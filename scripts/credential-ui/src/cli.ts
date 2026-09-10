import { randomBytes } from 'node:crypto';
import { lstat, mkdir, open, readFile, rename, unlink } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadManifest, nativeBackend, PublicError, validateManifest, type Manifest } from './config.ts';
import { loadPage, validateFields, validatePageUI } from './page.ts';

async function writeConfiguration(file: string, configuration: object) {
  await mkdir(path.dirname(file), { recursive: true });
  const temporary = file + '.' + randomBytes(8).toString('hex') + '.tmp';
  try {
    const handle = await open(temporary, 'wx', 0o600);
    try { await handle.writeFile(JSON.stringify(configuration, null, 2) + '\n', 'utf8'); await handle.sync(); }
    finally { await handle.close(); }
    await rename(temporary, file);
  } finally { await unlink(temporary).catch(() => {}); }
}
export async function configurePage(file: string, manifests: string[], options: Record<string, string>, dryRun = false) {
  if (Object.keys(options).some(key => !['title', 'label', 'save-label'].includes(key))) throw new PublicError('存在不支持的页面配置项。');
  let existing: { manifests: string[]; ui?: Record<string, string> } | undefined;
  try {
    const stat = await lstat(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink > 1) throw new PublicError('页面配置必须是独立的普通文件。');
    await loadPage(file);
    existing = JSON.parse(await readFile(file, 'utf8'));
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  // 命令参数按当前目录解析；写入页面文件后统一保存为相对该文件的路径。
  const paths = manifests.length ? manifests.map(item => path.relative(path.dirname(file), path.resolve(item)).split(path.sep).join('/')) : existing?.manifests ?? [];
  validateFields(await Promise.all(paths.map(item => loadManifest(path.resolve(path.dirname(file), item)))));
  const ui = { ...existing?.ui };
  for (const [flag, key] of [['title', 'title'], ['label', 'label'], ['save-label', 'saveLabel']])
    if (options[flag] !== undefined) ui[key] = options[flag];
  const configuration = { version: 1, manifests: paths, ui: validatePageUI(ui) };
  if (!dryRun) await writeConfiguration(file, configuration);
  return { status: dryRun ? 'preview' : 'configured', page: file, configuration };
}

export async function configureManifest(file: string, options: Record<string, string>, dryRun = false) {
  const allowed = ['id', 'label', 'credential', 'title', 'placeholder', 'save-label'];
  if (Object.keys(options).some(k => !allowed.includes(k))) throw new PublicError('存在不支持的配置项。');
  let existing: Manifest | undefined;
  try {
    const stat = await lstat(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink > 1) throw new PublicError('声明必须是独立的普通文件。');
    existing = await loadManifest(file);
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  if (existing && ((options.id && options.id !== existing.id) || (options.credential && options.credential !== existing.credential)))
    throw new PublicError('已有声明的身份和凭据引用不可改写。请为新凭据指定新的 --manifest 文件。');
  const draft: Record<string, unknown> = { version: 1, ...existing };
  for (const key of ['id', 'label', 'credential']) if (options[key] !== undefined) draft[key] = options[key];
  const ui = { ...existing?.ui };
  for (const [flag, key] of [['title', 'title'], ['placeholder', 'placeholder'], ['save-label', 'saveLabel']] as const)
    if (options[flag] !== undefined) ui[key] = options[flag];
  if (Object.keys(ui).length) draft.ui = ui;
  const manifest = validateManifest(draft);
  if (!dryRun) await writeConfiguration(file, manifest);
  return { status: dryRun ? 'preview' : 'configured', manifest: file, configuration: manifest };
}
async function main() {
  const [command, ...args] = process.argv.slice(2);
  if (!command || command === '--help') {
    process.stdout.write('configure [--manifest 文件] --id 标识 --label 用途 --credential 引用 [--title 标题] [--placeholder 占位文字] [--save-label 按钮文字] [--dry-run]\nconfigure-page --page 文件 [--manifest 声明（可重复，替换整组）] [--title 标题] [--label 用途] [--save-label 按钮文字] [--dry-run]\nstatus [--manifest 文件]\n');
    return;
  }
  const flags: Record<string, string> = {};
  const manifests: string[] = [];
  let dryRun = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--dry-run' && ['configure', 'configure-page'].includes(command)) { dryRun = true; continue; }
    if (command === 'configure-page' && args[i] === '--manifest' && args[i + 1] && !args[i + 1].startsWith('--')) { manifests.push(args[++i]); continue; }
    const name = args[i].replace(/^--/, '');
    if (!args[i].startsWith('--') || !args[i + 1] || args[i + 1].startsWith('--') || Object.hasOwn(flags, name))
      throw new PublicError('命令参数不正确。');
    flags[name] = args[++i];
  }
  if (command === 'configure-page') {
    if (!flags.page) throw new PublicError('请指定 --page 配置文件。');
    const file = path.resolve(flags.page); delete flags.page;
    process.stdout.write(JSON.stringify(await configurePage(file, manifests, flags, dryRun)) + '\n'); return;
  }
  const file = path.resolve(flags.manifest ?? fileURLToPath(new URL('../manifests/default.json', import.meta.url)));
  delete flags.manifest;
  if (command === 'configure') process.stdout.write(JSON.stringify(await configureManifest(file, flags, dryRun)) + '\n');
  else if (command === 'status' && !Object.keys(flags).length) {
    const m = await loadManifest(file);
    const backend = await nativeBackend(m.credential);
    const configured = (await backend.get()) !== undefined;
    process.stdout.write(JSON.stringify({ id: m.id, credential: m.credential, configured, storage: backend.name }) + '\n');
    if (!configured) process.exitCode = 2;
  } else throw new PublicError('命令不支持，请使用 --help。');
}
if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url)
  main().catch(error => {
    process.stderr.write((error instanceof PublicError ? error.message : '配置操作未完成，请检查文件位置与权限。') + '\n');
    process.exitCode = 1;
  });
