import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createStore, type CredentialBackend, type Manifest } from '../src/config.ts';
import { startServer } from '../src/server.ts';

const manifest = (name: string): Manifest => ({ version: 1, id: 'sample-skill', label: name, credential: 'sample-skill/' + name });
function memory() {
  const values = new Map<string, string>();
  const backend = (ref: string): CredentialBackend => ({
    name: '测试凭据库', get: async () => values.get(ref),
    set: async value => { values.set(ref, value); }, delete: async () => { values.delete(ref); }
  });
  return { values, backend };
}
test('同一个 Skill 的多个 key 独立保存、替换和删除', async () => {
  const m = memory(), a = manifest('first'), b = manifest('second');
  const sa = createStore(a, m.backend(a.credential)), sb = createStore(b, m.backend(b.credential));
  await sa.save({ value: 'FAKE_FIRST_VALUE', revision: (await sa.status()).revision });
  await sb.save({ value: 'FAKE_SECOND_VALUE', revision: (await sb.status()).revision });
  await sa.save({ value: 'FAKE_REPLACED_VALUE', revision: (await sa.status()).revision, replaceExisting: true });
  assert.equal(m.values.get(b.credential), 'FAKE_SECOND_VALUE');
  await m.backend(a.credential).delete();
  assert.equal((await sa.status()).configured, false); assert.equal((await sb.status()).configured, true);
});
test('多个端口共享浏览器 cookie 容器时，会话仍互不覆盖', async t => {
  const m = memory(), a = manifest('first'), b = manifest('second');
  const one = await startServer({ manifest: a, backend: m.backend(a.credential) });
  const two = await startServer({ manifest: b, backend: m.backend(b.credential) });
  t.after(one.close); t.after(two.close);
  const jar = new Map<string, string>();
  for (const app of [one, two]) {
    const auth = await fetch(app.origin + '/api/session', { method: 'POST',
      headers: { Origin: app.origin, Authorization: 'Bearer ' + app.bootstrap, 'X-Local-Request': '1' } });
    assert.equal(auth.status, 200);
    const cookie = auth.headers.get('set-cookie')!.split(';')[0], split = cookie.indexOf('=');
    jar.set(cookie.slice(0, split), cookie.slice(split + 1));
  }
  assert.equal(jar.size, 2);
  const cookie = [...jar].map(([k, v]) => k + '=' + v).join('; ');
  for (const [app, ref, value] of [[one, a.credential, 'FAKE_FIRST_VALUE'], [two, b.credential, 'FAKE_SECOND_VALUE']] as const) {
    const headers = { Cookie: cookie, Origin: app.origin, 'X-Local-Request': '1', 'Content-Type': 'application/json' };
    const response = await fetch(app.origin + '/api/meta', { headers }); assert.equal(response.status, 200);
    const meta = await response.json();
    const saved = await fetch(app.origin + '/api/save', { method: 'POST', headers, body: JSON.stringify({ revision: meta.revision, value }) });
    assert.equal(saved.status, 200);
    const status = await (await fetch(app.origin + '/agent/status', { headers: { Authorization: 'Bearer ' + app.bootstrap } })).json();
    assert.equal(status.credential, ref); assert.equal(status.status, 'saved');
  }
  assert.equal(m.values.size, 2);
  assert.equal((await fetch(one.origin + '/agent/status', { headers: { Authorization: 'Bearer ' + two.bootstrap } })).status, 401);
});
test('同一凭据的旧会话在其他会话保存后不能覆盖', async () => {
  const m = memory(), a = manifest('shared');
  const first = createStore(a, m.backend(a.credential)), second = createStore(a, m.backend(a.credential));
  const initial = await second.status();
  await first.save({ revision: (await first.status()).revision, value: 'FAKE_LATEST_VALUE' });
  await assert.rejects(second.save({ revision: initial.revision, value: 'FAKE_STALE_VALUE', replaceExisting: true }), /发生变化/);
  assert.equal(m.values.get(a.credential), 'FAKE_LATEST_VALUE');
});

async function session(app: Awaited<ReturnType<typeof startServer>>) {
  const headers: Record<string, string> = { Origin: app.origin, Authorization: 'Bearer ' + app.bootstrap,
    'X-Local-Request': '1', 'Content-Type': 'application/json' };
  const auth = await fetch(app.origin + '/api/session', { method: 'POST', headers });
  headers.Cookie = auth.headers.get('set-cookie')!.split(';')[0];
  return {
    meta: async () => (await fetch(app.origin + '/api/meta', { headers })).json(),
    save: (entries: object[]) => fetch(app.origin + '/api/save', { method: 'POST', headers, body: JSON.stringify({ entries }) }),
    agent: async () => (await fetch(app.origin + '/agent/status', { headers })).json(),
  };
}
test('同页多 key 真实 HTTP 保存、文案与状态脱敏', async t => {
  const m = memory(), fields = [manifest('one'), manifest('two')], emitted: object[] = [];
  const app = await startServer({ manifests: fields, backends: fields.map(field => m.backend(field.credential)),
    ui: { title: '连接服务', label: '双服务配置', saveLabel: '确认保存' }, onComplete: value => emitted.push(value) });
  t.after(app.close); const client = await session(app); const meta = await client.meta();
  assert.equal(meta.fields.length, 2); assert.equal(meta.page.title, '连接服务');
  const response = await client.save(meta.fields.map((field: any, index: number) => ({ credential: field.credential, revision: field.revision, value: 'FAKE_BATCH_' + index })));
  assert.equal(response.status, 200); const result = await response.json(); assert.equal(result.status, 'saved');
  assert.equal(m.values.get(fields[0].credential), 'FAKE_BATCH_0'); assert.equal(m.values.get(fields[1].credential), 'FAKE_BATCH_1');
  assert.equal(JSON.stringify([result, await client.meta(), await client.agent(), emitted]).includes('FAKE_BATCH_'), false);
});
test('整组预检拒绝无效项、重复项、越界引用、未确认替换和缺失项，零写入', async t => {
  const m = memory(), fields = [manifest('one'), manifest('two')];
  m.values.set(fields[0].credential, 'FAKE_OLD');
  const app = await startServer({ manifests: fields, backends: fields.map(field => m.backend(field.credential)) });
  t.after(app.close); const client = await session(app); const meta = await client.meta();
  const entries = meta.fields.map((field: any) => ({ credential: field.credential, revision: field.revision, value: 'FAKE_NEW', replaceExisting: true }));
  for (const invalid of [
    [entries[0]], [entries[0], { ...entries[1], value: 'multi\nline' }],
    [entries[0], entries[0]], [entries[0], { ...entries[1], credential: 'not/in/page' }],
    [{ ...entries[0], replaceExisting: false }, entries[1]],
    [entries[0], { ...entries[1], revision: 'stale' }],
    [entries[0], { ...entries[1], target: '/tmp/plaintext.json' }],
  ]) { assert.ok((await client.save(invalid)).status >= 400); assert.deepEqual([...m.values], [[fields[0].credential, 'FAKE_OLD']]); }
});
test('已有项留空不覆盖，中途失败保留已保存项并可仅重试失败项', async t => {
  const m = memory(), fields = [manifest('one'), manifest('two'), manifest('three'), manifest('four')];
  m.values.set(fields[0].credential, 'FAKE_KEEP');
  const backends = fields.map(field => m.backend(field.credential));
  let fail = true; const original = backends[2].set;
  backends[2].set = async value => { if (fail) throw Error(value); await original(value); };
  const app = await startServer({ manifests: fields, backends }); t.after(app.close);
  const client = await session(app); let meta = await client.meta();
  const response = await client.save(meta.fields.slice(1).map((field: any) => ({ credential: field.credential, revision: field.revision, value: 'FAKE_BATCH' })));
  const result = await response.json(); assert.equal(result.status, 'partial');
  assert.deepEqual(result.results.map((item: any) => item.status), ['saved', 'failed', 'not_attempted']);
  assert.equal(m.values.has(fields[3].credential), false);
  assert.equal((await client.agent()).status, 'partial'); assert.equal(JSON.stringify(result).includes('FAKE_BATCH'), false);
  assert.equal(m.values.get(fields[0].credential), 'FAKE_KEEP'); assert.equal(m.values.get(fields[1].credential), 'FAKE_BATCH');
  fail = false; meta = await client.meta();
  const retry = await client.save(meta.fields.slice(2).map((field: any) => ({ credential: field.credential, revision: field.revision, value: 'FAKE_RETRY' })));
  assert.equal((await retry.json()).status, 'saved'); assert.equal(m.values.get(fields[1].credential), 'FAKE_BATCH');
});
test('16 项预检并行读取，写入仍顺序执行且每项写前复验', async t => {
  const fields = Array.from({ length: 16 }, (_, index) => manifest('key-' + index));
  let active = 0, peak = 0, reads = 0, writes = 0;
  const backends = fields.map((): CredentialBackend => ({ name: '测试凭据库',
    get: async () => {
      reads++; active++; peak = Math.max(peak, active);
      await new Promise(resolve => setTimeout(resolve, 2)); active--; return undefined;
    },
    set: async () => { assert.equal(active, 0); writes++; }, delete: async () => {},
  }));
  const app = await startServer({ manifests: fields, backends }); t.after(app.close);
  const client = await session(app); const meta = await client.meta();
  peak = 0; reads = 0;
  const response = await client.save(meta.fields.map((field: any) => ({ credential: field.credential, revision: field.revision, value: 'FAKE_ONLY' })));
  assert.equal((await response.json()).status, 'saved');
  assert.equal(peak, 16); assert.equal(reads, 32); assert.equal(writes, 16);
});
test('页面拒绝重复引用、超限字段和空配置', async () => {
  const m = memory(), field = manifest('one');
  for (const fields of [[], [field, field], Array.from({ length: 17 }, (_, index) => manifest('key-' + index))])
    await assert.rejects(startServer({ manifests: fields, backends: fields.map(item => m.backend(item.credential)) }));
});
