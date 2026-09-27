import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

// Tools read only the coordinator's manifest, never arbitrary model-supplied paths.
export function createRepositoryTools(root, manifest, emit, limits = {}) {
  root = fs.realpathSync(root);
  const names = Object.keys(manifest.files).sort();
  const maxCalls = limits.maxCalls ?? 24;
  const maxChars = limits.maxChars ?? 48000;
  let calls = 0, chars = 0;
  function read(name) {
    if (!Object.hasOwn(manifest.files, name)) throw new Error('Path is outside the source manifest.');
    const resolved = fs.realpathSync(path.join(root, name));
    const relative = path.relative(root, resolved);
    if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Path escapes snapshot.');
    const data = fs.readFileSync(resolved);
    if (crypto.createHash('sha256').update(data).digest('hex') !== manifest.files[name])
      throw new Error('Snapshot file changed since capture.');
    return data.toString('utf8');
  }
  const string = { type: 'string', minLength: 1, maxLength: 300 };
  function tool(name, description, properties, required, action) {
    return { name, label: name, description, promptSnippet: description,
      parameters: { type: 'object', properties, required, additionalProperties: false },
      executionMode: 'sequential',
      async execute(id, input) {
        calls++;
        emit({ type: 'tool_start', tool: name, input });
        try {
          if (calls > maxCalls) throw new Error('Tool-call allowance exhausted; report missing context as a limitation.');
          let result = action(input);
          const allowance = Math.max(0, Math.min(8000, maxChars - chars));
          if (!allowance) throw new Error('Retrieved-context allowance exhausted; report missing context as a limitation.');
          const truncated = result.length > allowance;
          result = result.slice(0, allowance);
          chars += result.length;
          if (truncated) result += '\n[TRUNCATED: narrow the lookup; missing context must be reported.]';
          emit({ type: 'tool_result', tool: name, input, text: result, truncated, retrieved_chars: chars });
          return { content: [{ type: 'text', text: result }], details: { truncated } };
        } catch (error) {
          emit({ type: 'tool_error', tool: name, input, error: error.message });
          throw error;
        }
      }
    };
  }
  const tools = [
    tool('find_files', 'Find source paths by literal substring within the saved checkout.',
      { query: string }, ['query'], ({ query }) => {
        if (!query?.trim()) throw new Error('A non-empty query is required.');
        const matches = names.filter(n => n.toLowerCase().includes(query.toLowerCase()));
        return JSON.stringify({ matches: matches.slice(0, 80), total: matches.length });
      }),
    tool('search_text', 'Search a literal string in source files, optionally limited by a path substring. Returns line numbers.',
      { query: string, path_contains: { type: 'string', maxLength: 300 } }, ['query'], ({ query, path_contains = '' }) => {
        if (!query?.trim()) throw new Error('A non-empty query is required.');
        const matches = [];
        for (const name of names.filter(n => n.includes(path_contains))) {
          const lines = read(name).split(/\r?\n/);
          for (let i = 0; i < lines.length; i++) {
            if (lines[i].includes(query)) matches.push({ path: name, line: i + 1, text: lines[i].slice(0, 500) });
            if (matches.length >= 60) return JSON.stringify({ matches, truncated: true });
          }
        }
        return JSON.stringify({ matches, truncated: false });
      }),
    tool('read_lines', 'Read a numbered range of at most 160 lines from a source path found by lookup.',
      { path: string, start: { type: 'integer', minimum: 1 }, count: { type: 'integer', minimum: 1, maximum: 160 } },
      ['path', 'start', 'count'], ({ path: name, start, count }) => {
        if (!Number.isInteger(start) || start < 1 || !Number.isInteger(count) || count < 1 || count > 160)
          throw new Error('Invalid line range.');
        const lines = read(name).split(/\r?\n/);
        return lines.slice(start - 1, start - 1 + count).map((line, i) => `${start + i}: ${line}`).join('\n');
      })
  ];
  return { tools, stats: () => ({ tool_calls: calls, retrieved_chars: chars }) };
}

export function requestGuard(emit, inputLimit = 32000, maxRequests = 12) {
  let count = 0;
  return (model, context) => {
    // An estimate of serialized input, NOT a model-specific tokenizer or billing count.
    const estimated = Math.ceil(JSON.stringify(context).length / 3);
    const outputReserve = 4096;
    const limit = Math.min(inputLimit, (model.contextWindow || inputLimit + outputReserve) - outputReserve);
    count++;
    emit({ type: 'request_budget', request: count, estimated_tokens: estimated, input_limit: limit, output_reserve: outputReserve });
    if (count > maxRequests) throw new Error('Review request allowance exhausted.');
    if (estimated > limit) throw new Error('Estimated request context exceeds the configured allowance.');
    return outputReserve;
  };
}
