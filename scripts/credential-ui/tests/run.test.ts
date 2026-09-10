import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { tmpdir } from 'node:os';
import { execFile } from 'node:child_process';
import { parseBindings, prepareCommand } from '../src/run.ts';

async function fixture() {
  const dir = await mkdtemp(path.join(tmpdir(), 'credential-run-'));
  const files = [path.join(dir, 'first.json'), path.join(dir, 'second.json')];
  await Promise.all(files.map((file, i) => writeFile(file, JSON.stringify({ version: 1, id: 'sample-skill', label: '服务', credential: 'sample/key-' + i }))));
  return { dir, files, cleanup: () => rm(dir, { recursive: true, force: true }) };
}
test('多个 key 同时注入一个真实子进程，命令参数不包含值', async t => {
  const f = await fixture(); t.after(f.cleanup);
  const plan = await prepareCommand(['--manifest', f.files[0], '--env', 'FIRST_API_KEY', '--manifest', f.files[1], '--env', 'SECOND_API_KEY', '--',
    process.execPath, '-e', 'process.exit(process.env.FIRST_API_KEY && process.env.SECOND_API_KEY && process.env.FIRST_API_KEY !== process.env.SECOND_API_KEY ? 0 : 1)'],
    async ref => ref.endsWith('0') ? 'FAKE_FIRST_VALUE' : 'FAKE_SECOND_VALUE');
  assert.equal(plan.env.FIRST_API_KEY, 'FAKE_FIRST_VALUE'); assert.equal(plan.env.SECOND_API_KEY, 'FAKE_SECOND_VALUE');
  assert.equal(JSON.stringify(plan.args).includes('FAKE_'), false);
  await new Promise<void>((resolve, reject) => execFile(plan.command, plan.args, { env: plan.env }, error => error ? reject(error) : resolve()));
});
test('任一 key 缺失或后端失败，不返回可启动的命令，也不修改父环境', async t => {
  const f = await fixture(); t.after(f.cleanup);
  const args = ['--manifest', f.files[0], '--env', 'FIRST_API_KEY', '--manifest', f.files[1], '--env', 'SECOND_API_KEY', '--', 'unused'];
  const base = { KEEP: 'unchanged' };
  await assert.rejects(prepareCommand(args, async ref => ref.endsWith('0') ? 'FAKE_FIRST_VALUE' : undefined, base), /未配置/);
  await assert.rejects(prepareCommand(args, async () => { throw Error('FAKE_VALUE_MUST_NOT_LEAK'); }, base),
    error => error instanceof Error && !error.message.includes('FAKE_'));
  assert.deepEqual(base, { KEEP: 'unchanged' });
});
test('拒绝重复变量和不完整绑定，兼容单 key 的原入口', () => {
  assert.throws(() => parseBindings(['--env', 'DUP_KEY', '--env', 'DUP_KEY', '--', 'unused']), /重复/);
  assert.throws(() => parseBindings(['--manifest', 'a.json', '--manifest', 'b.json', '--env', 'A_KEY', '--', 'unused']));
  assert.throws(() => parseBindings(['--env', 'HOME', '--', 'unused']));
  assert.equal(parseBindings(['--env', 'SERVICE_API_KEY', '--', 'program', 'arg']).bindings.length, 1);
});
