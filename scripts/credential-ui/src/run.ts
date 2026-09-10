import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import { loadManifest, nativeBackend, PublicError } from './config.ts';

type Binding = { file: string; variable: string };
const defaultManifest = fileURLToPath(new URL('../manifests/default.json', import.meta.url));
const reserved = new Set(['PATH', 'HOME', 'SHELL', 'NODE_OPTIONS', 'LD_PRELOAD', 'DYLD_INSERT_LIBRARIES', 'PYTHONPATH', 'PYTHONSTARTUP', 'COMSPEC', 'SYSTEMROOT']);
export function parseBindings(args: string[]) {
  const split = args.indexOf('--');
  if (split < 0 || !args[split + 1]) throw new PublicError('请指定要启动的程序。');
  const bindings: Binding[] = [];
  const variables = new Set<string>();
  let pending: string | undefined;
  for (let i = 0; i < split; i += 2) {
    const value = args[i + 1];
    if (i + 1 >= split || !value || value.startsWith('--')) throw new PublicError('凭据绑定参数不完整。');
    if (args[i] === '--manifest' && pending === undefined) pending = value;
    else if (args[i] === '--env') {
      if (!/^[A-Z][A-Z0-9_]*$/.test(value) || reserved.has(value) || variables.has(value))
        throw new PublicError('环境变量名重复或不适合注入凭据。');
      bindings.push({ file: pending ?? defaultManifest, variable: value });
      variables.add(value); pending = undefined;
    } else throw new PublicError('凭据绑定参数不正确。');
  }
  if (pending !== undefined || !bindings.length || bindings.length > 16) throw new PublicError('请提供一至十六组完整的凭据绑定。');
  return { bindings, command: args[split + 1], args: args.slice(split + 2) };
}
export async function prepareCommand(
  args: string[],
  readCredential: (ref: string) => Promise<string | undefined> = async ref => (await nativeBackend(ref)).get(),
  baseEnv: NodeJS.ProcessEnv = process.env,
) {
  const plan = parseBindings(args);
  const manifests = await Promise.all(plan.bindings.map(binding => loadManifest(binding.file)));
  const env = { ...baseEnv };
  try {
    for (let i = 0; i < plan.bindings.length; i++) {
      const value = await readCredential(manifests[i].credential);
      if (!value) throw new PublicError('有凭据尚未配置，任务未启动。');
      env[plan.bindings[i].variable] = value;
    }
    return { ...plan, env };
  } catch (error) {
    for (const binding of plan.bindings) delete env[binding.variable];
    if (error instanceof PublicError) throw error;
    throw new PublicError('凭据读取未完成，任务未启动。');
  }
}
async function main() {
  const prepared = await prepareCommand(process.argv.slice(2));
  const child = spawn(prepared.command, prepared.args, { env: prepared.env, stdio: 'inherit', shell: false });
  for (const binding of prepared.bindings) delete prepared.env[binding.variable];
  child.once('error', () => { process.stderr.write('无法启动目标程序。\n'); process.exitCode = 1; });
  child.once('exit', code => { process.exitCode = code ?? 1; });
}
if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url)
  main().catch(error => {
    process.stderr.write((error instanceof PublicError ? error.message : '无法读取凭据或启动参数不正确。') + '\n');
    process.exitCode = 1;
  });
