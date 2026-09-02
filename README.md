# arch-drift-detection

Architecture drift detection GitHub Action. A self-hosted bot that reviews pull
requests for **architecture / layering drift** and posts inline comments on the
offending lines. Narrow by design: it only looks at production source, only flags
layering violations, and validates every model finding against the diff before it
becomes a comment.

---

## Progress

| # | Stage | Status |
|---|-------|--------|
| 0 | Lambda receives PR webhook, validates, logs the event | ✅ Done |
| 1 | Lambda → on-demand Fargate task; task logs the event and exits | ⬜ Next |
| 2 | Clone PR repo (GitHub CLI + PAT via env vars), retrieve diff | ⬜ Planned |
| 3 | **Annotation pass** — address changed lines, filter to source, build validation map | ✅ Done (local) |
| 4 | Oversized-diff guard — skip PRs too large for the context window | ⬜ Planned |
| 5 | Tokenizer measurement — quantify the annotation saving | ⬜ Planned |
| 6 | Model harness — start with Council of Experts | ⬜ Planned |

Stages 0 and 3 are built. Stages 1 and 2 are the "later phase" deferred in the
proposal below.

---

## Architecture Proposal, GitHub Webhook Handler

### Objective

The goal is to build a webhook handler that detects GitHub pull request events.
When a new pull request is created, GitHub fires a webhook event to our handler.
This is the foundation for a later pipeline that will clone the repository, check
out the pull request branch, and analyze the code changes.

This proposal focuses only on steps one and two, receiving and detecting the pull
request event. The heavier steps, cloning the repository and annotating the
difference, are intentionally deferred and noted in the recommendation.

### The Two Options

#### Option One, Cloudflare Workers

Cloudflare Workers is a lightweight serverless platform that runs small pieces of
code instantly when triggered. It scales to zero, meaning you pay nothing when
idle, and it offers a genuinely free tier of one hundred thousand requests per
day. It is ideal for receiving a webhook and reacting quickly. Its limitation is a
constrained runtime and short execution time, so it cannot clone large
repositories in process.

#### Option Two, AWS Fargate

AWS Fargate runs full containers with no runtime limits, so it can clone
repositories and perform heavy work. Used as a long-running service it costs money
when idle, but paired with AWS Lambda as a trigger it can be run as an on-demand
task. Lambda receives the event, spins up a Fargate task for that job, and the
task tears itself down when finished. This means paying only for the compute
minutes actually used.

### Recommendation

The recommended approach is to consolidate on a single stack, AWS. An AWS Lambda
function receives the GitHub webhook event. When heavier work is needed, Lambda
spins up an on-demand Fargate task that clones the repository and runs the analysis
pipeline, then tears itself down. Keeping the webhook handler and the compute layer
on the same platform avoids splitting across two vendors, which simplifies
deployment, monitoring, and reasoning about the system.

### How It Connects

1. A pull request is opened on GitHub.
2. GitHub fires a webhook event to our handler's URL.
3. An AWS Lambda function receives the event and validates it.
4. Lambda extracts the key details, such as pull request number, author, and branch.
5. Lambda logs the event. In a later phase, it spins up an on-demand Fargate task for heavier processing.

### Next Steps

1. Set up an AWS Lambda function and deploy a basic handler that receives the webhook and prints it to the console.
2. Register the webhook in the GitHub repository settings, pointing to the Lambda's URL, and subscribe to pull request events.
3. Verify the flow by opening a test pull request and confirming Lambda receives and logs the event.
4. In a later phase, add on-demand Fargate task handoff for cloning and diff analysis.

---

## Stage 3 — Annotation pass ✅ (verified locally)

`annotate.py` turns a raw unified diff into exactly what the model needs, and
nothing it doesn't. It does three jobs:

1. **Address every changed line.** A diff only marks lines `+` / `-`; it doesn't
   number them. Added lines are numbered against the new file, deleted lines
   against the old file, and unchanged context lines are dropped. Result: a flat
   list of `(path, line, change, code)` — each with a line number GitHub can
   anchor a comment to. Line-counting is delegated to the `unidiff` library
   rather than hand-parsed.

2. **Filter to production source.** Only files that can actually break a layering
   rule are kept (`.swift`, `.kt`, `.kts`); docs, generated JSON/HTML, assets,
   and **test files** are dropped before the model ever sees them. This is where
   the token saving comes from — not smarter parsing, just not sending files
   that can't violate a rule.

3. **Build the validation map.** From the same diff, a per-file map of the line
   ranges the PR actually changed. When the model later reports a finding,
   `is_in_diff()` checks the reported line against this map and drops it if the
   PR never touched that line — the guard against hallucinated locations.

### Evidence

Run against a real Alamofire PR (`git diff HEAD~5 HEAD`):

https://github.com/Alamofire/Alamofire

```
raw diff:              342 files,  4017 changed lines
after source filter:    33 files,  2613 changed lines
after test filter:      13 files,   378 changed lines   ← sent to model
```

**A tenth of the input**, and every remaining line is production code that could
actually break a rule. Sample of the resulting validation map:

```
Source/Core/Session.swift: 86-101, 233-245, 256-262, 1163-1196, ...
Source/Features/AuthenticationInterceptor.swift: 202-234, 236-242, 266-307, ...
Source/Features/Validation.swift: 27-38, 46-52
```

Verified on both a Linux container and the Windows dev machine — identical output.

### Run it

```
git diff HEAD~5 HEAD > pr.diff
python annotate.py pr.diff
```

Requires `pip install unidiff`. Make test diffs with `git diff`, never by hand —
hand-written diffs have wrong hunk headers and fail to parse.

---

## Design notes

- **The diff is used twice.** Once as the model's input, once as the ground truth
  its output is checked against. Built once, used twice.
- **Scope is deliberately narrow.** Only production source, only layering drift.
  Smaller input, lower cost, fewer ways for the model to go wrong.
- **Diff-only, for now.** The reviewer sees changed lines, not the whole repo, so
  it catches drift as it arrives rather than pre-existing drift. Whether the
  layering rules need surrounding file context (repo indexing) or can run on the
  annotated diff alone is the open design question before Stage 6.
