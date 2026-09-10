import { createHmac, randomBytes } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { execFile, spawn } from 'node:child_process';

export class PublicError extends Error {
  status: number;
  constructor(message: string, status = 400) { super(message); this.status = status; }
}
export type Manifest = {
  version: 1; id: string; label: string; credential: string;
  ui?: { title?: string; placeholder?: string; saveLabel?: string };
};
export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
export async function loadManifest(file: string): Promise<Manifest> {
  let m: unknown;
  try { m = JSON.parse(await readFile(file, 'utf8')); } catch { throw new PublicError('无法读取配置声明。'); }
  return validateManifest(m);
}
export function validateManifest(m: unknown): Manifest {
  if (!object(m) || m.version !== 1 || typeof m.id !== 'string' || !/^[a-z0-9-]{1,80}$/.test(m.id)
    || typeof m.label !== 'string' || !m.label.trim() || m.label.length > 120
    || typeof m.credential !== 'string' || !/^[a-z0-9][a-z0-9/_.-]{0,150}$/.test(m.credential)
    || Object.keys(m).some(k => !['version', 'id', 'label', 'credential', 'ui'].includes(k))) throw new PublicError('配置声明不合法。');
  if (m.ui !== undefined && (!object(m.ui) || Object.entries(m.ui).some(([k, v]) =>
    !['title', 'placeholder', 'saveLabel'].includes(k) || typeof v !== 'string' || !v.trim() || v.length > 80)))
    throw new PublicError('页面配置不合法。');
  return m as Manifest;
}
export interface CredentialBackend {
  name: string;
  get(): Promise<string | undefined>;
  set(value: string): Promise<void>;
  delete(): Promise<void>;
}
export const service = 'org.oiloil.skill-credentials';
const backendError = () => new PublicError('无法访问系统凭据库，请解锁或检查系统凭据服务后重试。', 503);

// Linux 显式使用 Secret Service，不走可能回退到临时 keyutils 的默认绑定。
function linuxBackend(credential: string): CredentialBackend {
  const attributes = ['service', service, 'account', credential];
  const run = (args: string[]): Promise<string | undefined> => new Promise((resolve, reject) => {
    execFile('secret-tool', args, { timeout: 15_000, maxBuffer: 32_768, encoding: 'utf8' }, (error, stdout, stderr) => {
      if (error) {
        if (args[0] === 'lookup' && error.code === 1 && !stderr.trim()) resolve(undefined);
        else reject(backendError());
      } else resolve(stdout.replace(/\r?\n$/, ''));
    });
  });
  return { name: 'Linux Secret Service', get: () => run(['lookup', ...attributes]),
    set: value => new Promise((resolve, reject) => {
      const child = spawn('secret-tool', ['store', '--label=Skill 凭据', ...attributes], { stdio: ['pipe', 'ignore', 'ignore'], timeout: 15_000, shell: false });
      child.once('error', () => reject(backendError()));
      child.stdin.on('error', () => reject(backendError()));
      child.once('close', code => code === 0 ? resolve() : reject(backendError()));
      child.stdin.end(value + '\n');
    }),
    delete: async () => { await run(['clear', ...attributes]); }
  };
}
export async function nativeBackend(credential: string): Promise<CredentialBackend> {
  if (process.platform === 'linux') return linuxBackend(credential);
  if (!['darwin', 'win32'].includes(process.platform)) throw new PublicError('当前系统暂不支持凭据保存。', 503);
  try {
    const { AsyncEntry } = await import('@napi-rs/keyring');
    const entry = new AsyncEntry(service, credential);
    return { name: process.platform === 'darwin' ? 'macOS 钥匙串' : 'Windows 凭据管理器',
      // 原生绑定的空结果在实际运行中可能为 null，统一为接口约定的 undefined。
      get: async () => { try { return (await entry.getPassword()) ?? undefined; } catch { throw backendError(); } },
      set: async value => { try { await entry.setPassword(value); } catch { throw backendError(); } },
      delete: async () => { try { await entry.deleteCredential(); } catch { throw backendError(); } }
    };
  } catch { throw backendError(); }
}
export function createStore(manifest: Manifest, backend: CredentialBackend) {
  const salt = randomBytes(32);
  let busy = false;
  async function status() {
    let value: string | undefined;
    try { value = await backend.get(); } catch { throw backendError(); }
    const revision = createHmac('sha256', salt).update(value === undefined ? 'missing:' : 'exists:').update(value ?? '').digest('hex');
    return { revision, configured: value !== undefined, storage: backend.name };
  }
  async function validate(input: unknown) {
    if (!object(input) || typeof input.value !== 'string' || !input.value.trim() || input.value.length > 2500
      || /[\r\n\0]/.test(input.value) || typeof input.revision !== 'string'
      || Object.keys(input).some(k => !['value', 'revision', 'replaceExisting'].includes(k))) throw new PublicError('请填写有效的单行密钥。');
    const current = await status();
    if (current.revision !== input.revision) throw new PublicError('凭据已发生变化，请刷新后重试。', 409);
    if (current.configured && input.replaceExisting !== true) throw new PublicError('已有凭据，请确认替换后保存。', 409);
    return { value: input.value.trim() };
  }
  async function save(input: unknown) {
    if (busy) throw new PublicError('正在保存，请稍后。', 409);
    busy = true;
    try {
      const checked = await validate(input);
      await backend.set(checked.value);
      return { status: 'saved', skill: manifest.id, credential: manifest.credential, configured: true };
    } catch (error) { if (error instanceof PublicError) throw error; throw backendError(); }
    finally { busy = false; }
  }
  return { status, save, validate };
}
