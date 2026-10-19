import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

let source = await readFile(new URL('../research_service/static/js/api.js', import.meta.url), 'utf8');
source = source.replace(/^import .*;\r?\n/gm, '');
globalThis.apiTestElements = {login: {hidden: true}, workspace: {hidden: false}};
source = 'const $ = id => globalThis.apiTestElements[id], notify = () => {}, emit = () => {};\n' + source;
const {api} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const ok = data => ({ok: true, status: 200, json: async () => data});
let calls = 0;
globalThis.fetch = async () => { calls++; return ok({ok: true}); };
assert.deepEqual(await api('/normal', undefined, undefined, {timeoutMs: 20}), {ok: true});
assert.equal(calls, 1);

calls = 0;
globalThis.fetch = async () => {
  calls++;
  return {ok: true, status: 200, json: async () => { throw new SyntaxError('bad JSON'); }};
};
await assert.rejects(api('/invalid', undefined, undefined, {timeoutMs: 20}), /無法讀取/);
assert.equal(calls, 1);

function stalledBody(signal) {
  return {ok: true, status: 200, json: () => new Promise((resolve, reject) => {
    const abort = () => reject(new DOMException('aborted', 'AbortError'));
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, {once: true});
  })};
}
calls = 0;
globalThis.fetch = async (path, {signal}) => { calls++; return stalledBody(signal); };
await assert.rejects(api('/post', {}, undefined, {timeoutMs: 20}), /逾時/);
assert.equal(calls, 1, 'POST must not retry after body timeout');
calls = 0;
await assert.rejects(api('/get', undefined, undefined, {timeoutMs: 20}), /逾時/);
assert.equal(calls, 2, 'GET retries body timeout once');

calls = 0;
globalThis.fetch = async (path, {signal}) => ++calls === 1 ? stalledBody(signal) : ok({recovered: true});
assert.deepEqual(await api('/retry', undefined, undefined, {timeoutMs: 20}), {recovered: true});
assert.equal(calls, 2);

const htmlError = status => ({ok: false, status, json: async () => { throw new SyntaxError('HTML response'); }});
calls = 0;
globalThis.fetch = async () => ++calls === 1 ? htmlError(503) : ok({recovered: true});
assert.deepEqual(await api('/html-503'), {recovered: true});
assert.equal(calls, 2, 'GET retries a 503 even when its body is HTML');
calls = 0;
globalThis.fetch = async () => { calls++; return htmlError(401); };
await assert.rejects(api('/html-401'), /HTTP 401/);
assert.equal(calls, 1);
assert.equal(globalThis.apiTestElements.login.hidden, false);
assert.equal(globalThis.apiTestElements.workspace.hidden, true);
console.log('PASS: normal/invalid JSON, POST timeout, GET timeout/recovery, HTML 503/401');
