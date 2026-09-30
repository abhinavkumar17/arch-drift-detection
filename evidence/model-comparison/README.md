# Three-model checkpoint — September 30, 2026

Same unchanged fifteen-file Android fixture, same prompt and source snapshot, all through OpenRouter. This was a comparison of independent broad reviews, not voting or specialized review passes. No comments were posted for this experiment. Android compilation and tests were deliberately not run before model review.

## Findings and limitations

All three detected the four seeded categories: blocking reset-button handling, repository bypass, UI mutation of ViewModel-owned undo state, and an inverted bulk mark-read value. This is one controlled fixture, not a general accuracy benchmark.

| Model | Finding quality observations |
| --- | --- |
| Claude | Five findings covering four categories; split state ownership into overlapping comments. |
| OpenAI | Four consolidated findings; checked supporting code and identified skipped repository analytics. |
| Gemini | Four findings without repository tool use; suggested a nonexistent datastore method and an invalid suspend-callback alternative. Detection does not establish fix correctness. |

## Usage and cost

| Model | Findings | Model requests | Tool calls | Input including cache | Output | Seconds | Recorded USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| anthropic/claude-sonnet-4.6 | 5 | 3 | 4 | 41,122 | 4,602 | 86.8 | $0.13466 |
| openai/gpt-5.5 | 4 | 8 | 11 | 92,103 | 3,469 | 47.3 | $0.23511 |
| google/gemini-2.5-pro | 4 | 1 | 0 | 11,015 | 2,910 | 28.4 | $0.04287 |

Total recorded cost: approximately **$0.413 USD**. These are saved provider usage costs, not an invoice. Input includes repeated context and cached tokens; price differs for input, cache, and output.

Claude used two searches and two file reads; OpenAI used three searches and eight reads; Gemini used neither. Source snapshot contained 462 files, but only requested excerpts were returned to the models. The initial assembled prompt was estimated at 11,471 tokens against a 16,000 preparation allowance. Per-request context allowance was 32,000 estimated tokens, with a 4,096 output limit, at most 12 model requests, 24 tool calls, and 48,000 retrieved characters. These are size/work limits, not dollar caps. Token estimates use characters divided by three, rounded up.

All three responses passed the updated schema and diff-location validator. Claude and OpenAI returned raw JSON; Gemini's wrapped JSON was accepted by normalization. Validation does not verify reasoning or suggested fixes.

## Inspect the evidence

- [Comparison totals](comparison.json) and [preparation report with fingerprints](preparation.json).
- [Exact assembled prompt](prompt.txt) and [unchanged test diff](input.diff). Expected answers were kept outside model inputs.
- Claude: [findings](claude/findings.json), [original response](claude/model-response.txt), [result](claude/result.json), [usage](claude/lookup-summary.json).
- OpenAI: [findings](openai/findings.json), [original response](openai/model-response.txt), [result](openai/result.json), [usage](openai/lookup-summary.json).
- Gemini: [findings](gemini/findings.json), [original response](gemini/model-response.txt), [result](gemini/result.json), [usage](gemini/lookup-summary.json).

These are selected unchanged evidence files. Full tool event streams and source snapshot remain local; the lookup-summary accounting label does not include costs, which are recorded separately in result.json. Preparation for this comparison used the local prompt builder, not Docker.
