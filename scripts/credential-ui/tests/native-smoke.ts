import { randomUUID } from 'node:crypto';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { nativeBackend, type CredentialBackend } from '../src/config.ts';
import { startServer } from '../src/server.ts';

const namespace = 'test/' + randomUUID();
const refs = [namespace + '/first', namespace + '/second'];
const entries: { backend: CredentialBackend; owned: boolean }[] = [];
const directory = await mkdtemp(path.join(tmpdir(), 'credential-native-'));
let phase = '初始化';
let cleanupFailed = false;
let app: Awaited<ReturnType<typeof startServer>> | undefined;
try {
  for (const ref of refs) {
    const backend = await nativeBackend(ref);
    if (await backend.get() !== undefined) throw Error();
    entries.push({ backend, owned: false });
  }
  const values = ['TEST_ONLY_A_' + randomUUID(), 'TEST_ONLY_B_' + randomUUID()];
  phase = '同页 HTTP 多 key 保存与回读';
  app = await startServer({ manifests: refs.map((credential, index) => ({ version: 1, id: 'sample-skill', label: '测试服务' + index, credential })) });
  const headers: Record<string, string> = { Origin: app.origin, Authorization: 'Bearer ' + app.bootstrap, 'X-Local-Request': '1', 'Content-Type': 'application/json' };
  const session = await fetch(app.origin + '/api/session', { method: 'POST', headers });
  headers.Cookie = session.headers.get('set-cookie')!.split(';')[0];
  const metadata = await (await fetch(app.origin + '/api/meta', { headers })).json();
  entries.forEach(entry => { entry.owned = true; });
  const saved = await fetch(app.origin + '/api/save', { method: 'POST', headers, body: JSON.stringify({
    entries: metadata.fields.map((field: { credential: string; revision: string }, index: number) => ({ credential: field.credential, revision: field.revision, value: values[index] }))
  }) });
  if (!saved.ok || (await saved.json()).status !== 'saved') throw Error();
  for (let i = 0; i < entries.length; i++) if (await entries[i].backend.get() !== values[i]) throw Error();
  phase = '替换隔离';
  values[0] = 'TEST_ONLY_A_REPLACED_' + randomUUID();
  await entries[0].backend.set(values[0]);
  if (await entries[1].backend.get() !== values[1]) throw Error();
  phase = '多 key 业务读取';
  const files = [path.join(directory, 'first.json'), path.join(directory, 'second.json')];
  for (let i = 0; i < files.length; i++)
    await writeFile(files[i], JSON.stringify({ version: 1, id: 'sample-skill', label: '测试服务', credential: refs[i] }));
  const script = fileURLToPath(new URL('../src/run.ts', import.meta.url));
  await new Promise<void>((resolve, reject) => execFile(process.execPath, [script,
    '--manifest', files[0], '--env', 'FIRST_API_KEY', '--manifest', files[1], '--env', 'SECOND_API_KEY', '--',
    process.execPath, '-e', 'process.exit(process.env.FIRST_API_KEY?.startsWith("TEST_ONLY_A_REPLACED_") && process.env.SECOND_API_KEY?.startsWith("TEST_ONLY_B_") ? 0 : 1)'],
    { timeout: 20_000 }, error => error ? reject(Error()) : resolve()));
  phase = '删除隔离';
  await entries[0].backend.delete();
  if (await entries[0].backend.get() !== undefined || await entries[1].backend.get() !== values[1]) throw Error();
  process.stdout.write('系统凭据库多 key 保存、替换隔离、业务读取和删除隔离验证通过（假凭据）。\n');
} catch {
  process.stderr.write('系统凭据库验证未通过，阶段：' + phase + '。\n'); process.exitCode = 1;
} finally {
  app?.close();
  for (const entry of entries) {
    if (!entry.owned) continue;
    try {
      if (await entry.backend.get() !== undefined) await entry.backend.delete();
      if (await entry.backend.get() !== undefined) cleanupFailed = true;
    } catch { cleanupFailed = true; }
  }
  await rm(directory, { recursive: true, force: true });
  if (cleanupFailed) {
    process.stderr.write('测试凭据清理失败，测试引用前缀：' + namespace + '\n'); process.exitCode = 1;
  } else process.stdout.write('测试凭据和临时声明已清理。\n');
}
