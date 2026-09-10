import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { loadPage } from '../src/page.ts';

test('页面配置真实 CLI：相对路径、独立字段文案、更新与只读预览', async t => {
  const dir = await mkdtemp(path.join(tmpdir(), 'credential-page-')); t.after(() => rm(dir, { recursive: true, force: true }));
  const files = ['one', 'two'].map(name => path.join(dir, name + '.json'));
  for (const [index, file] of files.entries()) await writeFile(file, JSON.stringify({ version: 1, id: 'sample-skill', label: '服务' + index,
    credential: 'sample/' + index, ui: { placeholder: '请输入测试凭据' + index } }));
  const page = path.join(dir, 'page.json');
  const script = fileURLToPath(new URL('../src/cli.ts', import.meta.url));
  const run = (args: string[]) => new Promise<number>(resolve => execFile(process.execPath,
    [script, 'configure-page', '--page', page, ...args], error => resolve(error ? 1 : 0)));
  const args = ['--manifest', files[0], '--manifest', files[1], '--title', '两项凭据'];
  assert.equal(await run(args), 0);
  assert.deepEqual(JSON.parse(await readFile(page, 'utf8')).manifests, ['one.json', 'two.json']);
  const loaded = await loadPage(page); assert.equal(loaded.manifests.length, 2); assert.equal(loaded.ui.title, '两项凭据');
  assert.equal(loaded.manifests[1].ui?.placeholder, '请输入测试凭据1');
  assert.equal(await run(['--label', '业务配置']), 0);
  const before = await readFile(page, 'utf8');
  assert.equal(await run(['--title', '只读预览', '--dry-run']), 0); assert.equal(await readFile(page, 'utf8'), before);
  assert.notEqual(await run(['--manifest', files[0], '--manifest', files[0]]), 0);
  assert.notEqual(await run(['--api-key', 'FAKE_ONLY']), 0);
  assert.equal(await readFile(page, 'utf8'), before);
});
