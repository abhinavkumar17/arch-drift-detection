# arch-drift-detection

Architecture drift detection GitHub Action. A self-hosted bot that reviews pull
requests for **architecture / layering drift** and posts inline comments on the
offending lines. Narrow by design: it only looks at production source, only flags
layering violations, and validates every model finding against the diff before it
becomes a comment.

---

## Progress# arch-drift-detection

Architecture drift detection GitHub Action. A self-hosted bot that reviews pull
requests for **architecture / layering drift** and posts inline comments on the
offending lines. Narrow by design: it only comments on production source, only
flags layering violations, and validates every model finding against the diff
before it becomes a comment.

---

## Progress

| # | Stage | Status |
|---|-------|--------|
| 0 | Lambda receives PR webhook, validates, logs the event | ✅ Done |
| 1 | Lambda → on-demand Fargate task; task logs the event and exits | ⬜ Next |
| 2 | Clone PR repo (GitHub CLI + PAT via env vars), retrieve diff | ⬜ Planned |
| 3 | **Annotation pass** — address every line, two-tier filter, build allow-list | ✅ Done (local) |
| 4 | Oversized-diff guard — trim to fit the context window | ⬜ Planned |
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
nothing it doesn't. It does three jobs.

### 1. Address every line

A diff marks lines `+` / `-` but never numbers them. The model can spot a problem
and still have no way to say where it lives — so a finding can't be placed as a
comment. The tags are the addressing scheme:

```
[NEW:L11] +     private let apiClient = NetworkLayer.APIClient()
[OLD:L14] -     private var legacyCache = [String: Any]()
[CTX:L12]       override func viewDidLoad() {
```

Two numbering systems run over the same file at once, so the side is not
optional — a bare line number is ambiguous:

| Tag | Change | Numbered against | GitHub side |
|-----|--------|------------------|-------------|
| `NEW:L#` | added | the new file | RIGHT |
| `OLD:L#` | deleted | the old file | LEFT |
| `CTX:L#` | unchanged | the new file | — (not commentable) |

Context lines are **kept**, not dropped, so the model can read around a change.
They cost tokens but nothing in correctness, since they never enter the
allow-list. Each `@@` header resets both counters; that counting is delegated to
the `unidiff` library rather than hand-parsed.

### 2. Filter in two tiers

Not every file that's worth reading is worth commenting on. `file_tier()` sorts
each path into one of three buckets:

| Tier | Files | Treatment |
|------|-------|-----------|
| `comment` | production `.swift`, `.kt`, `.kts` | model may read **and** comment |
| `context` | tests, `.md`, `.yml`, `.yaml`, `.json` | model may read, never comment |
| `drop` | lockfiles, `Pods/`, vendored, `/build/`, `/generated/`, `.min.js`, `.pbxproj`, `docs/` | never sent |

Tests earn their place in the middle tier deliberately: a test reaching into an
internal it has no business knowing about is one of the stronger drift signals
available. Dropping them loses that signal; letting the model comment on them
produces noise. Read-only is the right setting.

### 3. Build the allow-list

`allow_list()` produces, per file, the exact set of line numbers a comment may be
posted on — **split by side**:

```python
{"Source/Core/Session.swift": {"LEFT": {89, 90, ...}, "RIGHT": {89, 90, ...}}}
```

`is_in_diff(path, line, side, allowed)` is the guard. Every finding the model
returns goes through it; anything pointing outside the set is dropped before it
becomes a PR comment.

It is built from the annotated lines themselves, not from hunk headers. That
matters, and it's where the previous version was wrong: hunk headers carry
**new-file** numbering, while deleted lines carry **old-file** numbering. The old
guard compared one against the other. On a synthetic diff it annotated 16 deleted
lines and its own guard rejected 11 of them — and in the other direction accepted
11 unchanged lines as commentable. Building the allow-list from the same pass that
numbered the lines makes that class of mismatch impossible.

---

## Evidence

Run against a real Alamofire diff, checked in under `evidence/`:

https://github.com/Alamofire/Alamofire

```
after filtering:   36 files
                 2713 changed lines   ← commentable + readable
                 3342 context lines   ← readable only
```

Sample of the resulting allow-list. Note `Session.swift`: deleted lines run to
1455 while added lines stop at 1439 — the two numbering systems, side by side in
one file. This is exactly the gap a range-based guard falls into:

```
Source/Core/Session.swift
    LEFT  (deleted): 89, 90, ... 1448, 1455
    RIGHT (added):   89, 90, ... 1438, 1439

Source/Core/DataRequest.swift
    LEFT  (deleted): 108, 109, 110, 111
    RIGHT (added):   108

Source/Features/Validation.swift
    LEFT  (deleted): 30, 35, 49
    RIGHT (added):   30, 35, 49
```

Files in `evidence/`:

| File | What it is |
|------|-----------|
| `pr.diff` | the input — regenerate the rest from this |
| `annotation-run.txt` | full annotated output plus the allow-list |
| `test-run.txt` | 7 passing tests |

### Run it

```
pip install unidiff pytest

git diff HEAD~5 HEAD > pr.diff
python annotate.py pr.diff > annotation-run.txt
python -m pytest test_annotate.py -v > test-run.txt
```

Make test diffs with `git diff`, never by hand — hand-written diffs have wrong
hunk headers and `unidiff` rejects them.

On Windows, if the diff contains an emoji the console encoding will fail the run;
`main()` sets `sys.stdout` to UTF-8 to prevent that.

### Tests

`test_annotate.py` runs on diff strings alone — no AWS, no GitHub, no model. It
covers:

- deleted lines validate against their own numbering (the regression above)
- context lines reach the model but never the allow-list
- side matches change type, and the same number on the other side is a different place
- counters reset across `@@` boundaries
- file tiers: production, test, docs, noise
- findings outside the diff are rejected
- empty diff

---

## Design notes

- **The diff is used twice.** Once as the model's input, once as the ground truth
  its output is checked against. Built once, used twice — and by the same pass,
  so the two can't disagree about line numbers.
- **Read and comment are separate permissions.** What the model may look at is a
  wider set than what it may write on. Collapsing the two either loses signal or
  creates noise.
- **Diff-only, for now.** The reviewer sees changed lines and their surrounding
  context, not the whole repo, so it catches drift as it arrives rather than
  pre-existing drift.

### Open question

The guidance on context budget is to fill the window rather than build an index:
keep intake roughly 10% below the model's cap, so ~800–900k tokens for a 1M
window, and pre-process the diff and prompt to stay inside it.

That settles *how much* but not *what*. rgb-ios does not fit in 900k even filtered.
So: at that budget, what repo content travels alongside the diff, and how is it
selected? Until that's answered, Stage 4 has a limit to enforce but no priority
order to enforce it with.

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
