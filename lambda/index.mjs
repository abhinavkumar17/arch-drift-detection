import { createHmac, timingSafeEqual } from 'node:crypto';

const reply = (statusCode, body) => ({ statusCode, body });

export const handler = async (event) => {
  const secret = process.env.GITHUB_WEBHOOK_SECRET;
  const allowedRepo = process.env.ALLOWED_REPO;
  if (!secret || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(allowedRepo ?? '')) {
    return reply(503, 'Webhook is not configured');
  }
  const headers = Object.fromEntries(Object.entries(event?.headers ?? {})
    .map(([key, value]) => [key.toLowerCase(), value]));
  if (typeof event?.body !== 'string') return reply(400, 'Missing body');
  const raw = Buffer.from(event.body, event.isBase64Encoded ? 'base64' : 'utf8');
  const signature = headers['x-hub-signature-256'];
  if (typeof signature !== 'string' || !/^sha256=[a-fA-F0-9]{64}$/.test(signature)) {
    return reply(401, 'Invalid signature');
  }
  const expected = createHmac('sha256', secret).update(raw).digest();
  if (!timingSafeEqual(expected, Buffer.from(signature.slice(7), 'hex'))) {
    return reply(401, 'Invalid signature');
  }
  let payload;
  try {
    payload = JSON.parse(raw.toString('utf8'));
  } catch {
    return reply(400, 'Invalid JSON');
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return reply(400, 'Invalid payload');
  }
  if (headers['x-github-event'] !== 'pull_request' ||
      !['opened', 'synchronize', 'reopened'].includes(payload.action)) {
    return reply(200, 'Ignored');
  }
  const repo = payload.repository?.full_name;
  if (typeof repo !== 'string' || repo.toLowerCase() !== allowedRepo.toLowerCase()) {
    return reply(200, 'Ignored');
  }
  const prNumber = payload.pull_request?.number;
  if (!Number.isSafeInteger(prNumber) || prNumber <= 0) return reply(400, 'Invalid PR number');
  // Log identifiers only. Credentials and raw webhook contents must never enter this packet.
  const packet = { repo: allowedRepo, prNumber };
  console.log('Webhook accepted:', JSON.stringify(packet));
  // This remains an intake prototype: no Fargate task or review is launched yet.
  return reply(200, 'OK');
};
