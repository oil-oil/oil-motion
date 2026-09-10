"use strict";
const get = (id) => document.getElementById(id);
const form = get('credential-form');
const button = get('save');
let inputs = [];
let meta;
let busy = false;
const saveLabel = () => inputs.some((input, index) => input.value.trim() && meta.fields[index].configured)
    ? '替换并保存' : (meta.page.saveLabel ?? (meta.fields.length === 1 ? meta.fields[0].ui?.saveLabel : undefined) ?? '保存');
async function request(url, options = {}) {
    let response;
    try {
        response = await fetch(url, { ...options, credentials: 'same-origin', cache: 'no-store',
            headers: { 'Content-Type': 'application/json', 'X-Local-Request': '1', ...options.headers }, signal: AbortSignal.timeout(25_000) });
    }
    catch {
        throw new Error('未收到服务回复，请刷新确认保存结果，不要重复提交。');
    }
    const result = await response.json();
    if (!response.ok)
        throw new Error(result.error ?? '操作未完成，请重试。');
    return result;
}
function message(text) { const node = get('message'); node.textContent = text; node.hidden = false; }
function clearInputs() { inputs.forEach(input => { input.value = ''; }); }
function done() {
    clearInputs();
    form.hidden = true;
    get('heading').textContent = '已保存';
    get('hint').hidden = true;
    message('可以关闭此页，回到对话继续。');
}
function update() {
    button.disabled = busy || !meta || !['waiting', 'partial'].includes(meta.outcome)
        || !inputs.some(input => input.value.trim())
        || inputs.some((input, index) => !meta.fields[index].configured && !input.value.trim());
    if (meta && !busy)
        button.textContent = saveLabel();
}
function render() {
    clearInputs();
    inputs = [];
    const multi = meta.fields.length > 1;
    form.classList.toggle('multi', multi);
    const container = get('fields');
    container.replaceChildren();
    meta.fields.forEach((field, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'field';
        const label = document.createElement('label');
        label.htmlFor = 'secret-' + index;
        label.textContent = field.label;
        if (!multi)
            label.className = 'visually-hidden';
        if (field.configured) {
            const state = document.createElement('span');
            state.className = 'field-state';
            state.textContent = '已配置';
            label.append(state);
        }
        const input = document.createElement('input');
        input.id = label.htmlFor;
        input.type = 'password';
        input.autocomplete = 'new-password';
        input.autocapitalize = 'off';
        input.spellcheck = false;
        input.maxLength = 2500;
        input.required = !field.configured;
        input.setAttribute('aria-describedby', 'hint message');
        input.placeholder = field.configured ? '留空保留，输入则替换' : (field.ui?.placeholder ?? '粘贴 API Key');
        input.disabled = !['waiting', 'partial'].includes(meta.outcome);
        wrapper.append(label, input);
        container.append(wrapper);
        inputs.push(input);
    });
    get('context').textContent = meta.page.label ?? (multi ? meta.fields.length + ' 项凭据' : meta.fields[0].label);
    const title = meta.page.title ?? (multi ? '输入密钥' : meta.fields[0].ui?.title) ?? '输入密钥';
    get('heading').textContent = title;
    document.title = title;
    const storage = [...new Set(meta.fields.map(field => field.storage))].join('、');
    get('hint').textContent = '仅保存到' + storage + (meta.fields.some(field => field.configured) ? ' · 已配置项留空保留' : '');
    update();
    if (meta.outcome === 'saved')
        done();
    else if (meta.outcome === 'partial')
        message('上次仅部分保存。请核对已配置项，补填未完成项后重试。');
    else if (meta.outcome !== 'waiting')
        message('本次配置已结束，请重新打开入口。');
}
form.addEventListener('input', () => { update(); get('message').hidden = true; });
form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy || button.disabled)
        return;
    busy = true;
    update();
    inputs.forEach(input => { input.disabled = true; });
    button.textContent = '正在保存…';
    try {
        const entries = inputs.flatMap((input, index) => input.value.trim() ? [{ credential: meta.fields[index].credential,
                value: input.value, revision: meta.fields[index].revision, replaceExisting: meta.fields[index].configured }] : []);
        const result = await request('/api/save', { method: 'POST', body: JSON.stringify({ entries }) });
        if (result.status === 'saved') {
            meta.outcome = 'saved';
            done();
        }
        else {
            clearInputs();
            meta = await request('/api/meta');
            render();
            const statuses = { saved: '已保存', failed: '未确认成功', not_attempted: '未尝试' };
            message((result.results ?? []).map(item => (meta.fields.find(field => field.credential === item.credential)?.label ?? '凭据') + '：' + (statuses[item.status] ?? '请核对')).join('；')
                + '。请核对状态后重新填写未完成项。');
        }
    }
    catch (error) {
        clearInputs();
        try {
            meta = await request('/api/meta');
            render();
        }
        catch {
            meta.outcome = 'unknown';
        }
        if (meta.outcome !== 'saved')
            message(error instanceof Error ? error.message : '保存未完成，请刷新确认结果。');
    }
    finally {
        clearInputs();
        busy = false;
        inputs.forEach(input => { input.disabled = !['waiting', 'partial'].includes(meta.outcome); });
        update();
    }
});
window.addEventListener('pagehide', clearInputs);
async function initialize() {
    const token = location.hash.slice(1);
    if (token) {
        history.replaceState(null, '', location.pathname);
        await request('/api/session', { method: 'POST', headers: { Authorization: 'Bearer ' + token }, body: '{}' });
    }
    meta = await request('/api/meta');
    render();
}
initialize().catch(error => { get('context').textContent = '暂时无法连接'; message(error instanceof Error ? error.message : '请重新打开配置入口。'); });
