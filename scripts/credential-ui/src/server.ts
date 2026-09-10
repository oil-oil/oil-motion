import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import { createStore, loadManifest, nativeBackend, object, PublicError, type Manifest, type CredentialBackend } from './config.ts';
import { loadPage, validateFields, validatePageUI, type PageUI } from './page.ts';

const root = fileURLToPath(new URL('../', import.meta.url));
function equal(a: string, b: string) { const x = Buffer.from(a); const y = Buffer.from(b); return x.length === y.length && timingSafeEqual(x, y); }
export async function startServer(options: { manifest?: Manifest; manifests?: Manifest[]; ui?: PageUI; backend?: CredentialBackend; backends?: CredentialBackend[]; port?: number; ttlMs?: number; onComplete?: (result: object) => void }) {
  if (options.manifest && options.manifests) throw new PublicError('不能同时指定单项与多项声明。');
  const fields = validateFields(options.manifests ?? (options.manifest ? [options.manifest] : []));
  const ui = validatePageUI(options.ui ?? {});
  if ((options.backends && options.backends.length !== fields.length) || (options.backend && (fields.length !== 1 || options.backends)))
    throw new PublicError('凭据后端与字段数量不匹配。');
  const stores = await Promise.all(fields.map(async (field, index) => createStore(field,
    options.backends?.[index] ?? options.backend ?? await nativeBackend(field.credential))));
  const store = stores[0];
  const identity = fields.length === 1 ? { skill: fields[0].id, credential: fields[0].credential }
    : { credentials: fields.map(field => ({ skill: field.id, credential: field.credential })) };
  let lastResult: object | undefined;
  const bootstrap = randomBytes(32).toString('hex');
  const session = randomBytes(32).toString('hex');
  // 同一主机上的不同端口共享 cookie 命名空间，因此每个会话使用独立名称。
  const cookieName = 'credentials_session_' + randomBytes(12).toString('hex');
  let origin = '';
  let outcome = 'waiting';
  let saving = false;
  let completedTimer: ReturnType<typeof setTimeout> | undefined;
  const assets: Record<string, [string, string]> = {
    '/': ['index.html', 'text/html; charset=utf-8'], '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
    '/style.css': ['style.css', 'text/css; charset=utf-8'], '/favicon.svg': ['favicon.svg', 'image/svg+xml']
  };
  function json(res: ServerResponse, code: number, body: object) { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify(body)); }
  async function body(req: IncomingMessage) {
    if (req.headers['content-type'] !== 'application/json') throw new PublicError('请求格式不支持。', 415);
    const parts: Buffer[] = []; let size = 0;
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 256 * 1024) throw new PublicError('请求内容过大。', 413);
      parts.push(chunk);
    }
    try { return JSON.parse(Buffer.concat(parts).toString('utf8')) as unknown; }
    catch { throw new PublicError('请求格式不正确。'); }
  }
  const server = createServer(async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'");
    try {
      if (req.headers.host !== new URL(origin).host) throw new PublicError('请求来源不正确。', 403);
      const url = new URL(req.url ?? '/', origin);
      if (url.search) throw new PublicError('不接受 URL 查询参数。');
      if (req.headers.origin && req.headers.origin !== origin) throw new PublicError('不接受跨站请求。', 403);
      if (req.method === 'GET' && Object.hasOwn(assets, url.pathname)) {
        const [file, type] = assets[url.pathname];
        const content = await readFile(path.join(root, 'public', file));
        res.writeHead(200, { 'Content-Type': type }); res.end(content); return;
      }
      if (url.pathname === '/agent/status' && req.method === 'GET') {
        if (!equal(req.headers.authorization ?? '', `Bearer ${bootstrap}`)) throw new PublicError('无权访问。', 401);
        json(res, 200, { ...identity, status: outcome, result: lastResult }); return;
      }
      if (req.method === 'POST' && (req.headers.origin !== origin || req.headers['x-local-request'] !== '1'))
        throw new PublicError('请从本地配置页面提交。', 403);
      if (url.pathname === '/api/session' && req.method === 'POST') {
        if (!equal(req.headers.authorization ?? '', `Bearer ${bootstrap}`)) throw new PublicError('入口已失效，请重新打开工具提供的链接。', 401);
        res.setHeader('Set-Cookie', `${cookieName}=${session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${Math.ceil((options.ttlMs ?? 30 * 60_000) / 1000)}`);
        json(res, 200, { status: 'ready' }); return;
      }
      const cookies = (req.headers.cookie ?? '').split(';').map(c => c.trim());
      if (!cookies.some(c => equal(c, `${cookieName}=${session}`))) throw new PublicError('请重新打开工具提供的配置链接。', 401);
      if (url.pathname === '/api/meta' && req.method === 'GET') {
        const metadata = await Promise.all(fields.map(async (field, index) => ({ ...field, ...await stores[index].status() })));
        json(res, 200, { ...metadata[0], fields: metadata, page: ui, outcome }); return;
      }
      if (url.pathname === '/api/save' && req.method === 'POST') {
        if (!['waiting', 'partial'].includes(outcome) || saving) throw new PublicError('配置正在保存或已结束，请稍后确认状态。', 409);
        saving = true;
        try {
          const input = await body(req);
          let result;
          if (fields.length === 1 && object(input) && !Object.hasOwn(input, 'entries')) result = await store.save(input);
          else {
            if (!object(input) || Object.keys(input).some(key => key !== 'entries') || !Array.isArray(input.entries)
              || !input.entries.length || input.entries.length > fields.length) throw new PublicError('提交字段不合法。');
            const seen = new Set<string>();
            const entries = input.entries.map(entry => {
              if (!object(entry) || typeof entry.credential !== 'string' || seen.has(entry.credential)) throw new PublicError('提交凭据重复或不合法。');
              seen.add(entry.credential);
              const index = fields.findIndex(field => field.credential === entry.credential);
              if (index === -1) throw new PublicError('提交了页面之外的凭据。');
              const { credential, ...payload } = entry;
              return { index, payload };
            });
            // 所有格式、替换授权和版本先验证；系统存储不提供跨项事务。
            await Promise.all([
              ...entries.map(entry => stores[entry.index].validate(entry.payload)),
              ...fields.map(async (field, index) => {
                if (!seen.has(field.credential) && !(await stores[index].status()).configured)
                  throw new PublicError('请填写所有尚未配置的密钥。');
              }),
            ]);
            const results: { credential: string; status: string }[] = [];
            let failed = false;
            for (const entry of entries) {
              let status = 'not_attempted';
              if (!failed) {
                try { await stores[entry.index].save(entry.payload); status = 'saved'; }
                catch { status = 'failed'; failed = true; }
              }
              results.push({ credential: fields[entry.index].credential, status });
            }
            result = { ...identity, status: failed ? 'partial' : 'saved', results };
          }
          outcome = result.status;
          lastResult = result;
          json(res, 200, result);
          options.onComplete?.(result);
          if (outcome === 'saved') { completedTimer = setTimeout(close, 90_000); completedTimer.unref(); }
          return;
        } finally { saving = false; }
      }
      if (url.pathname === '/api/cancel' && req.method === 'POST') {
        if (!['waiting', 'partial'].includes(outcome) || saving) throw new PublicError('配置正在保存或已结束。', 409);
        outcome = 'cancelled'; json(res, 200, { status: outcome });
        options.onComplete?.({ ...identity, status: outcome });
        completedTimer = setTimeout(close, 500); completedTimer.unref(); return;
      }
      throw new PublicError('接口不存在。', 404);
    } catch (error) {
      if (!res.headersSent) json(res, error instanceof PublicError ? error.status : 500,
        { error: error instanceof PublicError ? error.message : '操作未完成，请检查系统凭据服务。' });
      else res.end();
    }
  });
  server.requestTimeout = 15_000;
  server.headersTimeout = 10_000;
  server.maxHeadersCount = 30;
  await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(options.port ?? 0, '127.0.0.1', () => resolve()); });
  const addr = server.address();
  if (!addr || typeof addr === 'string') throw new Error('无法启动本机服务。');
  origin = `http://127.0.0.1:${addr.port}`;
  const expiry = setTimeout(() => {
    if (['waiting', 'partial'].includes(outcome)) options.onComplete?.({ ...identity, status: 'expired', result: lastResult });
    close();
  }, options.ttlMs ?? 30 * 60_000);
  expiry.unref();
  function close() { clearTimeout(expiry); clearTimeout(completedTimer); server.close(); server.closeAllConnections(); }
  return { origin, url: `${origin}/#${bootstrap}`, bootstrap, close };
}

async function main() {
  const args = process.argv.slice(2);
  const manifestFiles: string[] = [];
  let pageFile: string | undefined;
  let port = 0;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--manifest' && args[i + 1]) manifestFiles.push(path.resolve(args[++i]));
    else if (args[i] === '--page' && args[i + 1] && !pageFile) pageFile = path.resolve(args[++i]);
    else if (args[i] === '--port' && /^\d+$/.test(args[i + 1] ?? '')) port = Number(args[++i]);
    else throw new PublicError('用法：npm start -- [--manifest 声明路径（可重复） | --page 页面配置] [--port 端口]');
  }
  if (port > 65535) throw new PublicError('端口不合法。');
  if (pageFile && manifestFiles.length) throw new PublicError('--page 与 --manifest 不能同时使用。');
  const page = pageFile ? await loadPage(pageFile) : {
    manifests: await Promise.all((manifestFiles.length ? manifestFiles : [path.join(root, 'manifests', 'default.json')]).map(loadManifest))
  };
  const app = await startServer({ ...page, port,
    onComplete: result => process.stdout.write(JSON.stringify(result) + '\n') });
  process.stdout.write(`本机配置页面（30 分钟内有效）：\n${app.url}\n`);
  process.once('SIGINT', app.close); process.once('SIGTERM', app.close);
}
if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  main().catch(() => { process.stderr.write('启动失败，请检查 Node.js 版本、声明文件和端口。\n'); process.exitCode = 1; });
}
