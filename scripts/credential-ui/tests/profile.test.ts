import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, writeFile, rm, readFile } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { loadProfile, prepareProfile, profileStatus } from '../src/profile.ts';
import { loadManifest, type CredentialBackend } from '../src/config.ts';
import { startServer } from '../src/server.ts';

test('真实分发配置：正式页面保存后可被对应业务环境读取，状态与参数不含值', async () => {
  const root = fileURLToPath(new URL('../', import.meta.url));
  const config = JSON.parse(await readFile(path.join(root, 'manifests/profiles.json'), 'utf8'));
  for (const name of Object.keys(config.profiles)) {
    const bindings = await loadProfile(name);
    const manifests = await Promise.all(bindings.map(b => loadManifest(b.manifest)));
    const values = new Map<string, string>();
    const backendFactory = async (ref: string): Promise<CredentialBackend> => ({
      name: 'fake', get: async () => values.get(ref),
      set: async value => { values.set(ref, value); }, delete: async () => { values.delete(ref); },
    });
    const app = await startServer({ manifests, backends: await Promise.all(manifests.map(m => backendFactory(m.credential))) });
    try {
      const headers: Record<string, string> = { Origin: app.origin, Authorization: 'Bearer ' + app.bootstrap, 'X-Local-Request': '1', 'Content-Type': 'application/json' };
      const session = await fetch(app.origin + '/api/session', { method: 'POST', headers });
      headers.Cookie = session.headers.get('set-cookie')!.split(';')[0];
      assert.equal((await fetch(app.origin)).status, 200);
      const meta = await (await fetch(app.origin + '/api/meta', { headers })).json();
      const saved = await fetch(app.origin + '/api/save', { method: 'POST', headers, body: JSON.stringify({ entries: meta.fields.map((f: { credential: string; revision: string }, i: number) => ({ credential: f.credential, revision: f.revision, value: 'TEST_ONLY_PROFILE_' + i })) }) });
      assert.equal((await saved.json()).status, 'saved');
      const status = await profileStatus(bindings, {}, async ref => values.get(ref));
      assert.equal(status.configured, true);
      assert.equal(JSON.stringify(status).includes('TEST_ONLY'), false);
      const plan = await prepareProfile(bindings, ['business-program', '--input', 'a b'], {}, async ref => values.get(ref));
      for (const b of bindings) assert.match(plan.env[b.env]!, /^TEST_ONLY_PROFILE_/);
      assert.equal(JSON.stringify(plan.args).includes('TEST_ONLY'), false);
      assert.deepEqual(plan.args, ['--input', 'a b']);
    } finally { app.close(); }
  }
});

test('已有环境凭据无需读取系统库；缺失或后端失败时不启动业务', async () => {
  const bindings = await loadProfile('default');
  const env = Object.fromEntries(bindings.map(b => [b.env, 'TEST_ONLY_ENV']));
  const noRead = async () => { throw Error('TEST_ONLY_FAILURE'); };
  assert.equal((await profileStatus(bindings, env, noRead)).configured, true);
  assert.equal((await prepareProfile(bindings, ['business'], env, noRead)).env[bindings[0].env], 'TEST_ONLY_ENV');
  await assert.rejects(prepareProfile(bindings, ['business'], {}, async () => undefined), /未配置/);
  await assert.rejects(prepareProfile(bindings, ['business'], {}, noRead), error => error instanceof Error && !error.message.includes('TEST_ONLY'));
});

test('配置拒绝跨目录声明、危险变量与未知业务', async t => {
  const dir = await mkdtemp(path.join(tmpdir(), 'credential-profile-')); t.after(() => rm(dir, { recursive: true, force: true }));
  await mkdir(path.join(dir, 'manifests'));
  for (const binding of [{ manifest: '../outside.json', env: 'API_KEY' }, { manifest: 'default.json', env: 'NODE_OPTIONS' }]) {
    await writeFile(path.join(dir, 'manifests/profiles.json'), JSON.stringify({ version: 1, profiles: { default: [binding] } }));
    await assert.rejects(loadProfile('default', dir));
  }
  await assert.rejects(loadProfile('unknown', dir));
});
