# arch-drift-detection

A self-hosted bot that reviews pull requests for **architecture / layering
drift** and posts inline comments on the offending lines.

Narrow by design: it only comments on production source, only flags layering
violations, and validates every model finding against the diff before it becomes
a comment.

---

## How the pipeline works

Five separate steps, in order. They are easy to collapse into one another, so
they are spelled out here deliberately.

**1. GitHub notifies us.** A PR is opened. GitHub fires a webhook to our Lambda
URL. The payload is JSON metadata only — PR number, author, branch, repo. **It
does not contain the diff.**

**2. Lambda validates and hands off.** Lambda verifies the webhook signature
(confirming the request is really from GitHub), extracts the few fields that
matter, and launches an on-demand Fargate task, passing those fields in as
environment variables. Lambda does no heavy work — it is short-lived and
memory-limited by design.

**3. Fargate collects the diff.** The task authenticates with a GitHub PAT,
clones the repo, checks out the PR branch, and produces the unified diff itself.
This is why Fargate exists: cloning a repo the size that would exceed
Lambda's limits.

**4. `annotate.py` prepares it for the model.** The diff is addressed and turned
into text the model can safely cite — plus an allow-list used to validate
whatever the model sends back.

**5. `pack.py` fits it to the budget.** Files are costed one by one against a
token budget and packed until the budget is spent. Size is the only thing that
excludes a file.

---

## Status

| # | Stage                                                                       | Status         |
| - | --------------------------------------------------------------------------- | -------------- |
| 0 | Lambda receives PR webhook, validates signature, logs the event             | ✅ Done         |
| 1 | Lambda → on-demand Fargate task; task logs the fields and exits             | ⬜ **Next**     |
| 2 | Clone PR repo (GitHub CLI + PAT), retrieve diff                             | ⬜ Planned      |
| 3 | Annotation pass — address every line, two-tier split, build allow-list      | ✅ Done (local) |
| 4 | Context budget guard — pack to a token budget, exclude on size only         | ✅ Done (local) |
| 5 | Measure the annotation pass against a real diff                             | ✅ Done (local) |
| 6 | Model harness — start with Council of Experts                               | ⬜ Planned      |

**Note on Stages 3–5.** They are built and tested, but they have only ever run on
a diff produced by hand with `git diff` on a local machine. They have never run on
a diff that Stage 2 fetched, because Stage 2 does not exist yet.

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

## Stage 3 — the annotation pass (Done locally for now)

### The problem

A unified diff is not addressable. It carries line numbers only in its `@@` hunk
headers — "starting at line 89, twelve lines" — while the individual lines
beneath them are unnumbered. A model reading it can see the code perfectly well
and still have no way to say *where* a problem lives. To cite a location it would
have to count lines down from the header, which models do unreliably.

Underneath that sits a second problem. A diff describes two versions of a file at
once: the file before the change and the file after. A deleted line has a
position in the old file; an added line has a position in the new one. So a bare
line number is ambiguous — old-file 40 and new-file 40 are different places.
GitHub's comment API reflects this directly: it will not accept a line without a
side, `LEFT` for the old file or `RIGHT` for the new.

Both problems have the same consequence. Without a per-line address that includes
its side, a finding cannot become a comment.


### The fix

`annotate.py` addresses both problems in a single pass over the diff. It does
three jobs.

### 1. Address every line

Every line the model sees carries a tag: which file it belongs to, its line
number, and which side that number is counted against.

```
[NEW:L11] +     private let apiClient = NetworkLayer.APIClient()
[OLD:L14] -     private var legacyCache = [String: Any]()
[CTX:L12]       override func viewDidLoad() {
```

| Tag      | Change    | Numbered against | GitHub side         |
| -------- | --------- | ---------------- | ------------------- |
| `NEW:L#` | added     | the new file     | RIGHT               |
| `OLD:L#` | deleted   | the old file     | LEFT                |
| `CTX:L#` | unchanged | the new file     | — (not commentable) |

Context lines are **kept**, not dropped, so the model can read around a change.
They cost tokens but nothing in correctness, since they never enter the
allow-list.

Counting is delegated to the `unidiff` library rather than hand-parsed. Each
`@@` header resets both counters, and getting that wrong by hand is the easiest
way to produce addresses that look right and point nowhere.

### 2. Sort files into tiers

Not every file worth reading is worth commenting on, so read and comment are
separate permissions. `file_tier()` sorts each path into one of two buckets:

| Tier      | Files                                                                     | Treatment                      |
| --------- | ------------------------------------------------------------------------- | ------------------------------ |
| `comment` | production `.swift`, `.kt`, `.kts`                                        | model may read **and** comment |
| `context` | everything else — tests, docs, lockfiles, project files, generated output  | model may read, never comment  |

Tests sit in the context tier deliberately. A test reaching into an internal it
has no business knowing about is one of the stronger drift signals available —
dropping tests loses that signal, while letting the model comment on them
produces noise. Read-only is the right setting.

Nothing is excluded by category. A file's path is a poor predictor of whether it
matters: code changing while its tests do not is itself a drift signal, and it is
invisible if tests never reach the model. The only thing that removes a file is
size, and that is handled in Stage 4.

This means the annotation pass is **not** a compression step. Measured on a
331-file Alamofire diff, it reduced the payload by 1.2% (163,426 → 161,447
estimated tokens). Its value is addressability, not size.

### 3. Build the allow-list

The same pass that numbers the lines also records which of them a comment may be
posted on — per file, **split by side**:

```
{"Source/Core/Session.swift": {"LEFT": {89, 90, ...}, "RIGHT": {89, 90, ...}}}
```

`is_in_diff(path, line, side, allowed)` is the guard. Every finding the model
returns goes through it, and anything pointing outside the set is dropped before
it becomes a PR comment. That covers both a model inventing a location and a
model commenting on a file it was only allowed to read.

It is built from the annotated lines themselves, **not** from hunk headers —
and that is where the previous version was wrong. Hunk headers carry new-file
numbering while deleted lines carry old-file numbering, so the old guard was
comparing one against the other. On a synthetic diff it annotated 16 deleted
lines and its own guard rejected 11 of them, while in the other direction it
accepted 11 unchanged lines as commentable. Building the allow-list from the
pass that numbered the lines makes that class of mismatch impossible.

---

## Stage 4 — the context budget guard

### The budget

A context window is a per-request ceiling, not a quota. Everything sent in one
call — prompt template, diff, and the model's own response — has to fit inside
it. So the payload gets a share, not the whole thing:

```
1,000,000 tokens   context window
      × 0.80       reserve 20% for the prompt template and the response
= 800,000 tokens   payload budget
```

Tokens are estimated by character count, not by a tokenizer library:

```python
tokens = ceil(len(text) / 3.0)
```

### How packing works

`pack.py` walks the annotated file blocks in order, costs each one, and adds it
to the payload while the running total stays under budget. Every decision is
logged: path, tier, characters, tokens, running total, and status. That log is
the evidence artefact, written to `evidence/pack-run.txt`.

### What a real diff looks like

Run against `evidence/pr.diff` (Alamofire, `HEAD~5..HEAD`):

```
331 files   161,335 tokens   20.2% of budget   0 excluded
```

The guard never fired. The composition is the more interesting result:

| Group                          | Files | Tokens  | Share |
| ------------------------------ | ----- | ------- | ----- |
| `docs/` generated HTML         | 300   | 134,131 | 83.1% |
| duplicates `docs/docsets/`     | 151   |  70,045 | 43.4% |
| project files (pbxproj, scheme)|  10   |  10,547 |  6.5% |
| `Gemfile.lock`                 |   1   |   3,373 |  2.1% |
| `Source/`                      |   7   |   2,613 |  1.6% |
| **`comment` tier (total)**     | **8** | **4,014** | **2.5%** |

So 97.5% of what the model reads, it cannot comment on.

---

### Evidence: budget enforcement

Three runs against Alamofire, same code, bigger diff each time.

| run | files in | tokens | % of budget | files excluded |
|---|---|---|---|---|
| `HEAD~5` | 331 | 161,335 | 20.2% | 0 |
| `HEAD~10` | 362 | 289,022 | 36.1% | 0 |
| `HEAD~20` | 335 | 799,214 | 99.9% | 48 |

The first two fit with room to spare. `HEAD~20` is the first diff big enough to
run out of budget — 1,341,153 raw tokens against a ceiling of 800,000 — so the
guard had no choice but to drop files.

The log separates two cases. One file was costed and didn't fit
(`exceeds remaining budget`). The other 47 were never costed at all, because the
budget was already gone by the time they came up
(`budget exhausted before reached`).

### Annotation overhead

Annotation adds line addresses (`[CTX:L11]`, `[NEW:L14]`) to every line, which
costs tokens rather than saving them:

| run | raw tokens | annotated tokens | overhead |
|---|---|---|---|
| `HEAD~5` | 163,426 | 161,447 | −1.2% |
| `HEAD~10` | 272,948 | 289,141 | +5.9% |
| `HEAD~20` | 1,341,153 | 1,445,811 | +7.8% |

This is the price of addressable findings and is stable across runs. Note that
`pack.py` reports a single `reduction:` figure that nets this overhead against
excluded files; the two effects are separated above.

### Reproduce

Everything under `evidence/` can be regenerated from scratch:

```
pip install unidiff pytest

git diff HEAD~5 HEAD > pr.diff
python annotate.py pr.diff > annotation-run.txt
python pack.py pr.diff > pack-run.txt
python -m pytest test_annotate.py -v > test-run.txt
```

## Tests

`test_annotate.py` runs on diff strings alone — no AWS, no GitHub, no model. So
Stage 3's correctness can be verified today, while the stages around it are
still unbuilt.
