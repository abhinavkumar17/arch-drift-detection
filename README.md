# arch-drift-detection

A self-hosted bot that reviews pull requests for **architecture / layering
drift** and posts inline comments on the offending lines.

Narrow by design: it only comments on production source, only flags layering
violations, and validates every model finding against the diff before it becomes
a comment.

---

## How the pipeline works

Four separate steps, in order. They are easy to collapse into one another, so
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
This is why Fargate exists: cloning a repo the size of `rgb-ios` would exceed
Lambda's limits.

**4. `annotate.py` prepares it for the model.** The diff is addressed, filtered,
and turned into text the model can safely cite — plus an allow-list used to
validate whatever the model sends back.

---

## Status

| # | Stage                                                                       | Status         |
| - | --------------------------------------------------------------------------- | -------------- |
| 0 | Lambda receives PR webhook, validates signature, logs the event             | ✅ Done         |
| 1 | Lambda → on-demand Fargate task; task logs the fields and exits             | ⬜ **Next**     |
| 2 | Clone PR repo (GitHub CLI + PAT), retrieve diff                             | ⬜ Planned      |
| 3 | Annotation pass — address every line, two-tier filter, build allow-list     | ✅ Done (local) |
| 4 | Oversized-diff guard                                                        | ⬜ Planned      |
| 5 | Tokenizer measurement — quantify the annotation saving                      | ⬜ Planned      |
| 6 | Model harness — start with Council of Experts                               | ⬜ Planned      |

**Note on Stage 3.** It is built and tested, but it has only ever run on a diff
produced by hand with `git diff` on a local machine. It has never run on a diff
that Stage 2 fetched, because Stage 2 does not exist yet.

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
separate permissions. `file_tier()` sorts each path into one of three buckets:

| Tier      | Files                                                                                | Treatment                      |
| --------- | ------------------------------------------------------------------------------------ | ------------------------------ |
| `comment` | production `.swift`, `.kt`, `.kts`                                                   | model may read **and** comment |
| `context` | tests, `.md`, `.yml`, `.yaml`, `.json`                                               | model may read, never comment  |
| `drop`    | lockfiles, `Pods/`, `vendor/`, `build/`, `generated/`, `.min.*`, `.pbxproj`, `docs/` | never sent                     |

Tests sit in the middle tier deliberately. A test reaching into an internal it
has no business knowing about is one of the stronger drift signals available —
dropping tests loses that signal, while letting the model comment on them
produces noise. Read-only is the right setting.

Anything in `drop` cannot violate a layering rule, so sending it buys nothing.
This is where the token saving comes from: not smarter parsing, just not sending
files that can't be wrong.

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

### Run it

```
pip install unidiff pytest

git diff HEAD~5 HEAD > pr.diff
python annotate.py pr.diff > annotation-run.txt
python -m pytest test_annotate.py -v > test-run.txt
```

Make test diffs with `git diff`, never by hand — hand-written diffs have wrong
hunk headers and `unidiff` rejects them. On Windows, `main()` sets `sys.stdout`
to UTF-8 so an emoji in the diff doesn't fail the run.

### Tests

`test_annotate.py` runs on diff strings alone — no AWS, no GitHub, no model. It
covers: deleted lines validating against their own numbering (the regression
above), context lines reaching the model but never the allow-list, side matching
change type, counters resetting across `@@` boundaries, file tiering, findings
outside the diff being rejected, and the empty diff.

---

## Design notes

- **The diff is used twice.** Once as the model's input, once as the ground truth
  its output is checked against. Built by the same pass, so the two cannot
  disagree about line numbers.
- **Read and comment are separate permissions.** What the model may look at is a
  wider set than what it may write on. Collapsing the two either loses signal or
  creates noise.
- **Diff-only, for now.** The reviewer sees changed lines and their surrounding
  context, not the whole repo — so it catches drift as it arrives, not
  pre-existing drift.

---

