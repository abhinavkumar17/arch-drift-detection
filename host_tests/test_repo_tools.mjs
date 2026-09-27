import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRepositoryTools, requestGuard } from '../repo_tools.mjs';

test('lookup is scoped, logged, bounded, and detects changed evidence', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'review-tools-'));
  try {
    const text = 'class Store\nfun updateData() {}\n';
    fs.writeFileSync(path.join(root, 'Store.kt'), text);
    const manifest = { files: { 'Store.kt': crypto.createHash('sha256').update(text).digest('hex') } };
    const events = [];
    const lookup = createRepositoryTools(root, manifest, event => events.push(event));
    const invoke = (name, input) => lookup.tools.find(t => t.name === name).execute('test', input);
    assert.match((await invoke('find_files', { query: 'Store' })).content[0].text, /Store.kt/);
    assert.match((await invoke('search_text', { query: 'updateData' })).content[0].text, /"line":2/);
    assert.equal((await invoke('read_lines', { path: 'Store.kt', start: 2, count: 1 })).content[0].text, '2: fun updateData() {}');
    await assert.rejects(invoke('read_lines', { path: '../outside.txt', start: 1, count: 1 }), /manifest/);
    await assert.rejects(invoke('read_lines', { path: 'Store.kt', start: 1, count: 200 }), /range/);
    fs.writeFileSync(path.join(root, 'Store.kt'), 'different');
    await assert.rejects(invoke('read_lines', { path: 'Store.kt', start: 1, count: 1 }), /changed/);
    assert.ok(events.some(e => e.type === 'tool_result' && e.tool === 'read_lines'));
    const bounded = createRepositoryTools(root, manifest, () => {}, { maxCalls: 1, maxChars: 3 });
    const result = await bounded.tools[0].execute('test', { query: 'Store' });
    assert.ok(result.details.truncated);
    await assert.rejects(bounded.tools[0].execute('test', { query: 'Store' }), /allowance/);
  } finally { fs.rmSync(root, { recursive: true }); }
});

test('request allowance counts history and retrieved context on each call', () => {
  const events = [];
  const guard = requestGuard(e => events.push(e), 100, 2);
  assert.equal(guard({ contextWindow: 10000 }, { messages: ['small'] }), 4096);
  assert.throws(() => guard({ contextWindow: 10000 }, { messages: ['small', 'x'.repeat(500)] }), /context/);
  assert.throws(() => guard({ contextWindow: 10000 }, {}), /request allowance/);
  assert.equal(events.length, 3);
});
