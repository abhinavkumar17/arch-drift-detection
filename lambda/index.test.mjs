import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { handler } from './index.mjs';

test('webhook authenticates raw bytes, filters events, and never logs credentials', async () => {
  const previous = { ...process.env };
  const originalLog = console.log;
  const logs = [];
  console.log = (...args) => logs.push(args.join(' '));
  process.env.GITHUB_WEBHOOK_SECRET = 'test-webhook-secret';
  process.env.GITHUB_TOKEN = 'test-token-must-not-leak';
  process.env.ALLOWED_REPO = 'example/android';
  const payload = { action: 'opened', repository: { full_name: 'example/android' }, pull_request: { number: 7 } };
  const event = (value = payload, base64 = false) => {
    const body = typeof value === 'string' ? value : JSON.stringify(value);
    return { body: base64 ? Buffer.from(body).toString('base64') : body, isBase64Encoded: base64,
      headers: { 'X-GitHub-Event': 'pull_request', 'X-Hub-Signature-256':
        'sha256=' + createHmac('sha256', process.env.GITHUB_WEBHOOK_SECRET).update(body).digest('hex') } };
  };
  try {
    assert.equal((await handler(event())).body, 'OK');
    assert.equal((await handler(event(payload, true))).body, 'OK');
    const tampered = event(); tampered.body += ' ';
    assert.equal((await handler(tampered)).statusCode, 401);
    const unsigned = event(); delete unsigned.headers['X-Hub-Signature-256'];
    assert.equal((await handler(unsigned)).statusCode, 401);
    const malformed = event(); malformed.headers['X-Hub-Signature-256'] = 'sha256=bad';
    assert.equal((await handler(malformed)).statusCode, 401);
    assert.equal((await handler(event('{broken'))).statusCode, 400);
    assert.equal((await handler(event('null'))).statusCode, 400);
    assert.equal((await handler(event({ ...payload, action: 'closed' }))).body, 'Ignored');
    assert.equal((await handler(event({ ...payload, repository: { full_name: 'other/repo' } }))).body, 'Ignored');
    const other = event(); other.headers['X-GitHub-Event'] = 'issues';
    assert.equal((await handler(other)).body, 'Ignored');
    assert.equal((await handler(event({ ...payload, pull_request: {} }))).statusCode, 400);
    delete process.env.GITHUB_WEBHOOK_SECRET;
    assert.equal((await handler({})).statusCode, 503);
    assert.equal(logs.length, 2);
    assert.ok(!logs.join('').includes('test-token-must-not-leak'));
    assert.ok(!logs.join('').includes('test-webhook-secret'));
  } finally {
    console.log = originalLog;
    for (const key of ['GITHUB_WEBHOOK_SECRET', 'GITHUB_TOKEN', 'ALLOWED_REPO']) {
      if (previous[key] === undefined) delete process.env[key]; else process.env[key] = previous[key];
    }
  }
});
