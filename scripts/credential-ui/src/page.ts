import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { loadManifest, object, PublicError, validateManifest, type Manifest } from './config.ts';

export type PageUI = { title?: string; label?: string; saveLabel?: string };
export function validatePageUI(ui: unknown): PageUI {
  if (!object(ui) || Object.entries(ui).some(([key, value]) =>
    !['title', 'label', 'saveLabel'].includes(key) || typeof value !== 'string' || !value.trim() || value.length > 120))
    throw new PublicError('页面文案配置不合法。');
  return ui as PageUI;
}
export function validateFields(fields: Manifest[]): Manifest[] {
  if (!Array.isArray(fields) || fields.length < 1 || fields.length > 16) throw new PublicError('每页需要 1 至 16 项凭据声明。');
  fields.forEach(validateManifest);
  if (new Set(fields.map(field => field.credential)).size !== fields.length) throw new PublicError('同一页不能重复引用相同凭据。');
  return fields;
}
export async function loadPage(file: string) {
  let value: unknown;
  try { value = JSON.parse(await readFile(file, 'utf8')); } catch { throw new PublicError('无法读取页面配置。'); }
  if (!object(value) || value.version !== 1 || Object.keys(value).some(key => !['version', 'manifests', 'ui'].includes(key))
    || !Array.isArray(value.manifests) || !value.manifests.length || value.manifests.length > 16
    || value.manifests.some(item => typeof item !== 'string' || !item.trim())) throw new PublicError('页面配置不合法。');
  const ui = validatePageUI(value.ui ?? {});
  const manifests = validateFields(await Promise.all(value.manifests.map(item => loadManifest(path.resolve(path.dirname(file), item)))));
  return { manifests, ui };
}
