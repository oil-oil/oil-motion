import assert from 'node:assert/strict';
import { test } from 'node:test';
import { request as httpRequest } from 'node:http';
import { fileURLToPath } from 'node:url';
import { readFile } from 'node:fs/promises';
import { createStore, loadManifest, type CredentialBackend } from '../src/config.ts';
import { startServer } from '../src/server.ts';

const manifest = await loadManifest(fileURLToPath(new URL('../manifests/default.json', import.meta.url)));
const fake = 'TEST_ONLY_NOT_A_REAL_SECRET_12345';
test('通用页面默认使用中性色，不引入未经配置的品牌色', async () => {
  const css = await readFile(new URL('../public/style.css', import.meta.url), 'utf8');
  for (const match of css.matchAll(/#([0-9a-f]{6})(?:[0-9a-f]{2})?\b/gi)) {
    const color = match[1];
    assert.equal(color.slice(0, 2), color.slice(2, 4));
    assert.equal(color.slice(2, 4), color.slice(4, 6));
  }
});
function memory(initial?: string) {
  let value = initial;
  let writes = 0;
  const backend: CredentialBackend = { name: '测试凭据库', get: async () => value,
    set: async v => { value = v; writes++; }, delete: async () => { value = undefined; } };
  return { backend, value: () => value, writes: () => writes };
}
test('首次保存只写入凭据后端；状态与结果不包含密钥', async () => {
  const m = memory();
  const store = createStore(manifest, m.backend);
  const before = await store.status();
  assert.equal(before.configured, false);
  const saved = await store.save({ revision: before.revision, value: fake });
  assert.equal(m.value(), fake);
  const after = await store.status();
  assert.equal(after.configured, true);
  assert.equal(JSON.stringify({ saved, after }).includes(fake), false);
  assert.equal('target' in after, false);
});
test('已有值需要确认替换，旧版本请求不能覆盖新值', async () => {
  const m = memory('TEST_OLD');
  const store = createStore(manifest, m.backend);
  const before = await store.status();
  await assert.rejects(store.save({ revision: before.revision, value: fake }), /确认替换/);
  assert.equal(m.writes(), 0);
  await store.save({ revision: before.revision, value: fake, replaceExisting: true });
  await assert.rejects(store.save({ revision: before.revision, value: 'TEST_STALE', replaceExisting: true }), /发生变化/);
  assert.equal(m.value(), fake);
});
test('凭据服务不可用时明确失败，不回退文件，不泄漏底层错误', async () => {
  const bad: CredentialBackend = { name: '不可用', get: async () => { throw Error(fake); },
    set: async () => { throw Error(fake); }, delete: async () => {} };
  await assert.rejects(createStore(manifest, bad).status(), e => e instanceof Error && !e.message.includes(fake) && /系统凭据/.test(e.message));
  const m = memory(); m.backend.set = async () => { throw Error(fake); };
  const store = createStore(manifest, m.backend);
  await assert.rejects(store.save({ revision: (await store.status()).revision, value: fake }), e => e instanceof Error && !e.message.includes(fake));
});
test('拒绝路径、旧 JSON 请求、空值、多行及超长密钥', async () => {
  const m = memory(); const store = createStore(manifest, m.backend);
  const revision = (await store.status()).revision;
  for (const input of [{ revision, value: fake, target: '/tmp/unwanted.json' },
    { revision, values: { api_key: fake } }, { revision, value: '' },
    { revision, value: 'one\ntwo' }, { revision, value: 'x'.repeat(2501) }])
    await assert.rejects(store.save(input));
  assert.equal(m.writes(), 0);
});
test('HTTP 认证、Host 和跨站保护、脱敏及默认单字段占位框', async t => {
  const m = memory(); const emitted: object[] = [];
  const app = await startServer({ manifest, backend: m.backend, onComplete: v => emitted.push(v) });
  t.after(app.close);
  assert.equal((await fetch(app.origin + '/api/meta')).status, 401);
  const wrongHost = await new Promise<number | undefined>((resolve, reject) => {
    const req = httpRequest(app.origin, { headers: { Host: 'attacker.example' } }, res => { res.resume(); resolve(res.statusCode); });
    req.on('error', reject); req.end();
  });
  assert.equal(wrongHost, 403);
  const html = await fetch(app.origin);
  assert.match(html.headers.get('Content-Security-Policy')!, /frame-ancestors 'none'/);
  assert.equal((await html.text()).match(/<input\b/g)?.length, 1);
  const headers: Record<string, string> = { Origin: app.origin, 'X-Local-Request': '1', 'Content-Type': 'application/json', Authorization: 'Bearer ' + app.bootstrap };
  const auth = await fetch(app.origin + '/api/session', { method: 'POST', headers, body: '{}' });
  assert.equal(auth.status, 200); headers.Cookie = auth.headers.get('set-cookie')!.split(';')[0];
  const meta = await (await fetch(app.origin + '/api/meta', { headers })).json();
  assert.equal(meta.label, manifest.label);
  assert.deepEqual(meta.ui, manifest.ui);
  const payload = { revision: meta.revision, value: fake };
  const post = (extras: Record<string, string>) => fetch(app.origin + '/api/save', { method: 'POST', headers: { ...headers, ...extras }, body: JSON.stringify(payload) });
  assert.equal((await post({ Origin: 'https://attacker.example' })).status, 403);
  assert.equal((await post({ 'X-Local-Request': '' })).status, 403);
  const result = await post({}); assert.equal(result.status, 200);
  const visible = [await result.text(), JSON.stringify(emitted)];
  visible.push(await (await fetch(app.origin + '/api/meta', { headers })).text());
  const agent = await (await fetch(app.origin + '/agent/status', { headers })).json();
  assert.equal(agent.status, 'saved'); visible.push(JSON.stringify(agent));
  assert.equal(visible.some(v => v.includes(fake)), false);
  assert.equal((await post({})).status, 409); assert.equal(m.writes(), 1);
});
test('取消不写凭据，取消后不能再保存', async t => {
  const m = memory(); const app = await startServer({ manifest, backend: m.backend }); t.after(app.close);
  const headers: Record<string, string> = { Origin: app.origin, 'X-Local-Request': '1', 'Content-Type': 'application/json', Authorization: 'Bearer ' + app.bootstrap };
  const auth = await fetch(app.origin + '/api/session', { method: 'POST', headers, body: '{}' });
  headers.Cookie = auth.headers.get('set-cookie')!.split(';')[0];
  assert.equal((await fetch(app.origin + '/api/cancel', { method: 'POST', headers, body: '{}' })).status, 200);
  assert.equal((await fetch(app.origin + '/api/save', { method: 'POST', headers, body: '{}' })).status, 409);
  assert.equal(m.writes(), 0);
});
