import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('../src/cli.ts', import.meta.url));
const run = (args: string[]) => new Promise<{ code: number; output: string }>(resolve => {
  execFile(process.execPath, [script, 'configure', ...args], { encoding: 'utf8' },
    (error, stdout, stderr) => resolve({ code: error ? 1 : 0, output: stdout + stderr }));
});
test('真实 CLI：创建、局部修改、幂等与只读预览', async t => {
  const dir = await mkdtemp(path.join(tmpdir(), 'credential-configure-')); t.after(() => rm(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'service.credential.json');
  const create = ['--manifest', file, '--id', 'sample-skill', '--label', '服务凭据', '--credential', 'sample/service/default'];
  assert.equal((await run(create)).code, 0);
  const first = await readFile(file, 'utf8');
  assert.equal((await run(create)).code, 0); assert.equal(await readFile(file, 'utf8'), first);
  assert.equal((await run(['--manifest', file, '--title', '连接服务', '--placeholder', '输入访问凭据'])).code, 0);
  const updated = JSON.parse(await readFile(file, 'utf8'));
  assert.equal(updated.credential, 'sample/service/default'); assert.equal(updated.ui.title, '连接服务');
  const before = await readFile(file, 'utf8');
  assert.equal((await run(['--manifest', file, '--label', '预览', '--dry-run'])).code, 0);
  assert.equal(await readFile(file, 'utf8'), before);
});
test('真实 CLI：拒绝更换已有身份、未知字段和不完整声明', async t => {
  const dir = await mkdtemp(path.join(tmpdir(), 'credential-configure-')); t.after(() => rm(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'service.credential.json');
  await run(['--manifest', file, '--id', 'sample-skill', '--label', '服务凭据', '--credential', 'sample/service/default']);
  const before = await readFile(file, 'utf8');
  assert.equal((await run(['--manifest', file, '--credential', 'other/account'])).code, 1);
  assert.equal((await run(['--manifest', file, '--api-key', 'FAKE_VALUE_FOR_TEST_ONLY'])).code, 1);
  assert.equal(await readFile(file, 'utf8'), before);
  assert.equal((await run(['--manifest', path.join(dir, 'incomplete.json'), '--label', '缺字段'])).code, 1);
});
