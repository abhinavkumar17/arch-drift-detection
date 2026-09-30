# Architecture drift review

## Objective and approach

Build a self-hosted PR reviewer that prioritizes project architecture guidelines while allowing other supported correctness findings. Assemble an annotated diff and review instructions, enforce estimated context budgets, let Pi coordinate model review and read-only repository lookup, validate the response, and publish supported findings to changed PR lines.

## Current results

- **Local PR-to-comment loop demonstrated:** a saved review was posted to the intended Android PR line; repeating publication detected the existing review. [Posted test comment](https://github.com/abhinavkumar17/nowinandroid/pull/1#discussion_r4117992844).
- **Three-model comparison complete:** Claude Sonnet 4.6, OpenAI GPT 5.5, and Gemini 2.5 Pro found all four seeded issue categories in the same fifteen-file fixture. Fix quality, duplication, tool use, and cost differed. Total recorded model cost was about **$0.413 USD**. [Findings, cost, tokens, tools, and original responses](evidence/model-comparison/README.md).
- **Prompt assembly and budget gates demonstrated:** complete prompts are checked before review, with additional estimated checks during repository-aware review. Oversized preparation stops before calling a model. [Prompt evidence](evidence/prompt-test/pr.diff.report.json) and [Docker overflow proof](evidence/live-docker-test/twenty-commits/summary.json).
- No AWS/Fargate setup

These are controlled prototype results, not evidence of general review accuracy, production readiness, or superiority over Copilot. The Android fixture was not compiled or executed. Token estimates are approximate; format and location validation do not establish semantic correctness.

## Local flow

The local PR-to-comment path has been demonstrated. Preparation runs in Docker; Pi and the publisher run on the laptop. OpenRouter supplies the selected model remotely.

```mermaid
flowchart TD
    PR["GitHub PR"] --> ACQUIRE
    subgraph LOCAL["Developer laptop — implemented"]
        ACQUIRE["PR coordinator: review_pr.py<br/>Fetch fixed revisions and build diff"] --> PREP
        DIFF["Saved diff + optional source checkout"] --> PREP
        subgraph DOCKER["Docker — preparation only"]
            PREP["entrypoint.py + core.prompt<br/>Annotate diff and assemble prompt"] --> GATE{"Complete prompt<br/>within estimated budget?"}
        end
        GATE -->|No| STOP["Save failure evidence; stop"]
        GATE -->|Yes| PI["review_local.py + Pi adapter<br/>Model and tool conversation<br/>Per-request budget checks"]
        PI <-->|Read-only lookup| SOURCE["Tracked source snapshot<br/>Find files, search text, read lines"]
        PI --> VALIDATE["Response validator<br/>JSON fields and changed-line locations"]
        VALIDATE --> SAVE["Local evidence<br/>Findings, responses, usage and tool logs"]
        SAVE --> PUBLISH["publish_review.py<br/>Preview; recheck revisions and duplicates"]
        PUBLISH -->|Explicit posting command| COMMENT["Publish validated review"]
    end
    PI <-->|Model requests and responses| OR["OpenRouter<br/>Selected model"]
    COMMENT --> GH["GitHub inline PR comment"]
```

Saved-diff reviews can stop at local evidence. Posting requires a PR-linked run and an explicit publication step. Validation checks format and location, not reasoning accuracy. Both review entry points require OpenRouter, with Claude Sonnet 4.6 as the default; they do not fall back to Codex sign-in. The fifteen-file comparison used local prompt preparation instead of Docker.

## Development milestones: why, tests, and evidence

### 1. Acquire a reproducible diff

**Why:** a review needs an identifiable code change. Moving branch names alone are insufficient for reproducing a result or posting to the right revision.

**What we did:** first used saved Alamofire diffs, then verified live repository fetching in Docker. The later local PR coordinator fetches fixed base/head commits into a separate checkout, derives the diff from their merge base, and records the revisions. It checks for revision changes before treating a review as current.

**Result and proof:** saved inputs make the early experiments repeatable; live preparation demonstrated repository-to-diff acquisition. See the [small saved diff](evidence/annotation-test/pr.diff), [large saved diff](evidence/annotation-test/pr-20.diff), and [live five-commit run](evidence/live-docker-test/five-commits/summary.json). Private-repository and unattended cloud authentication remain pending.

### 2. Annotate changes and validate comment locations

**Why:** a raw diff has hunk coordinates, but a model needs an explicit file, line, and side for each finding. Deleted lines use old-file numbering; added lines use new-file numbering. Mixing these can put a valid observation on the wrong line.

**What we did:** annotation labels added, deleted, and context lines and builds a side-aware allow-list. Production Swift/Kotlin files are commentable; other files remain readable context under the current policy. Validation rejects findings outside allowed changed lines. Annotation provides addresses; it is not intended to compress the diff.

**Tests and result:** synthetic annotation tests exercise numbering and allowed locations. The historical investigation found an earlier hunk-based guard rejected 11 of 16 deleted lines and incorrectly accepted 11 context lines; deriving the allow-list from annotated lines corrected that mismatch. Saved Alamofire runs exercise the same approach on larger diffs.

**Proof:** [annotation output](evidence/annotation-test/annotation-run.txt), [large annotation output](evidence/annotation-test/annotation-run-20.txt), [historical test output](evidence/annotation-test/test-run.txt), and [annotation tests](tests/test_annotate.py). The saved test log is a historical snapshot, not the current full-suite result.

### 3. Explore diff budgets, then check the complete prompt

**Why:** counting only the diff misses instructions, guidelines, and output requirements. We needed evidence that the final assembled input is checked before a model is called.

**First experiment — diff-only packing:** the packer kept file blocks until an 800,000-token estimated allowance was reached. The small saved run kept 161,335 estimated tokens; the large run kept 799,214 and excluded 48 files. This demonstrated size enforcement, but could omit review context. [Small packing log](evidence/annotation-test/pack-run.txt), [large packing log](evidence/annotation-test/pack-run-20.txt).

**Current approach — assemble first, then gate:** insert guidelines and all annotated diff blocks into the template, estimate the complete prompt, and stop if it exceeds the configured allowance. The complete-prompt path does not trim files to make the input fit.

| Historical complete-prompt test | Estimated input tokens | Allowance | Result |
| --- | ---: | ---: | --- |
| Small saved diff | 164,870 | 800,000 | Fits |
| Large saved diff | 1,449,353 | 800,000 | Correctly rejected as oversized |

**Proof:** [small assembled prompt](evidence/prompt-test/pr.diff.prompt.txt), [small report](evidence/prompt-test/pr.diff.report.json), [large assembled prompt](evidence/prompt-test/pr-20.diff.prompt.txt), and [large report](evidence/prompt-test/pr-20.diff.report.json). Reports include input fingerprints. The large case passed its expected-overflow test; it did not pass for submission to a model.

**Limit:** these historical allowances are experiment settings, not current model limits. All these checks use character count divided by three, rounded up. They prove the gate's behavior, not exact tokenizer-level context fit or a spending cap.

### 4. Automate preparation and verify it in Docker

**Why:** preparation needed one repeatable command, consistent failure handling, and saved evidence rather than manual steps.

**What we tested:** the runner executes preparation tests, acquires or reads a diff, annotates it, assembles the prompt, and records the budget outcome. Later stages stop on failure. Both saved-input and live-fetch Docker runs were exercised.

**Result:** historical Docker validation passed all 27 preparation tests. The live five-commit input fit at 164,857 estimated tokens; the twenty-commit input stopped at 1,449,340 against an 800,000 allowance. No model was called and no files were trimmed. Slight differences from the earlier prompt snapshot reflect separate runs and template versions.

**Proof:** [five-commit summary](evidence/live-docker-test/five-commits/summary.json), [twenty-commit summary](evidence/live-docker-test/twenty-commits/summary.json), and their [saved evidence folders](evidence/live-docker-test). Application test success does not mean the reviewed Android code is defect-free.

### 5. Integrate Pi and controlled repository lookup locally

**Why:** a diff may reveal a suspicious dependency without showing its consequences. The reviewer needs a way to inspect related code while controlling context growth and recording its activity.

**What we did:** the local coordinator starts Pi after preparation passes. Repository-aware review uses read-only file discovery, text search, and line-reading tools over a tracked-source snapshot. Our adapter limits tool work, estimates each request's context, and records usage. Pi manages the model/tool conversation. These are application controls, not an operating-system sandbox.

**Tests and result:** a small Android state-ownership violation produced a finding; a manual reverse/fix case produced none. A five-file settings-reset experiment detected direct datastore access bypassing a repository in both diff-only and lookup-enabled reviews. The lookup run made three searches, three reads, and three model requests, totaling 17,008 reported tokens including repeated/cached context. This demonstrated lookup, not an accuracy improvement over the baseline.

**Proof:** the [original milestone and per-request table](README-history.md#local-review-milestone--september-27-2026) preserve the earlier results and local artifact location. The newer [three-model checkpoint](evidence/model-comparison/README.md) attaches repository-aware findings and usage directly to the repo. Earlier generated run folders remain local and are not presented as downloadable evidence.

### 6. Broaden review scope and make response handling reliable

**Why:** architecture guidelines should guide attention without suppressing genuine correctness defects. Separately, useful findings should not be lost merely because a model wraps JSON in Markdown.

**What we tested:** the original architecture-focused instructions missed a synthetic blocking-code problem; broader instructions detected it. We aligned the template and Pi adapter, then checked architecture violation, blocking defect, and valid-change cases. Models detected the intended defects, but several responses failed the old raw-JSON-only parser.

**Change and result:** the parser now accepts a single unambiguous JSON object surrounded by prose or Markdown, while rejecting malformed or ambiguous responses and still validating fields and locations. The template requests JSON only. The previous offline verification reported 87 passing Python tests and successful parsing/location checks for all nine saved responses; no new model calls were needed for that fix. This documentation edit does not rerun those tests.

**Proof and limit:** format tests (local, not yet published), publisher tests (local, not yet published), and [new comparison responses and validation results](evidence/model-comparison/README.md). The earlier three-case response sets remain local. Parser acceptance is distinct from whether a suggested fix is correct.

### 7. Complete the local PR-to-comment loop

**Why:** producing a finding locally is only part of the goal; it must reach the intended changed line on the reviewed PR without being stale or duplicated.

**What we did:** the PR coordinator records exact revisions. The publisher creates a preview, checks current revisions, submits against the reviewed commit, and records publication. An existing-review marker and a local submission journal help prevent duplicate posting.

**Result and proof:** the five-file Android test produced an [inline comment on the intended ViewModel line](https://github.com/abhinavkumar17/nowinandroid/pull/1#discussion_r4117992844); repeating publication detected the existing review. See PR coordinator tests (local, not yet published) and publisher tests (local, not yet published). Cloud concurrency and durable duplicate tracking still need work; the local demonstration does not establish production-safe distributed posting.

### 8. Compare models on a larger unchanged fixture — latest checkpoint

**Why:** small examples did not show enough about differences in evidence gathering, suggestion quality, cost, and token use.

**What we tested:** the same fifteen-file Android diff, prompt, source snapshot, and limits were given independently to Claude Sonnet 4.6, OpenAI GPT 5.5, and Gemini 2.5 Pro through OpenRouter. The fixture includes two architecture categories, two correctness categories, and supporting changes. Expected answers were excluded from model inputs. At the user's request, the Android fixture was not built or repaired first.

**Result:** all three found the four intended categories. Claude returned five findings with an overlap; OpenAI returned four and checked the analytics consequence; Gemini returned four without tool use but proposed some incorrect fixes. Total recorded cost was about $0.413 USD. All responses passed the revised validation. This is a controlled comparison, not voting, and not proof of equal quality or broad accuracy.

**Proof:** [comparison tables, tokens, costs, tools, and raw findings](evidence/model-comparison/README.md), [exact prompt](evidence/model-comparison/prompt.txt), and [fixture diff](evidence/model-comparison/input.diff). Review experiments stop here pending Pratik's input.

### 9. Move the verified local workflow to Fargate — next target

**Why:** the eventual review should run without a developer's laptop or interactive sign-in. Fargate is the selected target for an on-demand container worker.

**Already demonstrated:** manual preparation in Fargate with S3 evidence upload, as recorded in the historical milestone. That was preparation only; a directly linked cloud run artifact is not included in this documentation package.

**Still pending:** packaging Pi and publication with preparation, unattended GitHub App/OpenRouter authentication, a manual end-to-end Fargate run, and then automatic event triggering. The old infrastructure alternatives remain in history; they are not competing current plans. Detailed remaining work is listed below.

## Review this checkpoint

1. Inspect the [model comparison and linked raw findings](evidence/model-comparison/README.md).
2. Inspect the [assembled prompt](evidence/model-comparison/prompt.txt) and [fixture diff](evidence/model-comparison/input.diff).
3. Check historical assembly evidence: [complete prompt](evidence/prompt-test/pr.diff.prompt.txt), [budget report](evidence/prompt-test/pr.diff.report.json), and [oversized Docker summary](evidence/live-docker-test/twenty-commits/summary.json).
4. Inspect the [published local test comment](https://github.com/abhinavkumar17/nowinandroid/pull/1#discussion_r4117992844).

Older implementation explanations and experiments are preserved in [development history](README-history.md); their status statements are historical.

## Pending work and AWS sequence

The three-model comparison is the current stopping point. Further model comparisons, council voting, and focused-review experiments are parked pending technical review.

| Step | Work remaining |
| --- | --- |
| Save the checkpoint | Documentation and selected evidence are published in this checkpoint. Review and publish the remaining local implementation changes separately; request Pratik's feedback. |
| Full container | Package preparation, Pi, repository lookup, validation, evidence saving, and posting in one reproducible image; verify locally. |
| Unattended authentication | Configure OpenRouter credentials and a GitHub App identity through runtime secrets; replace personal interactive sign-in. |
| Manual Fargate run | Fetch exact PR revisions, run a review, save durable evidence and logs, and verify posting with revision and duplicate checks. |
| Automatic triggering | Verify webhook signatures and event eligibility; connect job launch with retry, timeout, duplicate-delivery, and concurrency handling. |
| Operations | Establish least-privilege access, durable publication tracking, monitoring, cost controls, and failure recovery. |

Serverless workers can be disposable, but the system still needs durable evidence and job/publication state outside the container. Existing local duplicate controls must be reviewed for concurrent cloud jobs.

Questions for Pratik: should the next review strategy use focused passes rather than council voting; what criteria should merge, score, and select findings; and which model mix should be used? AWS packaging can progress independently of those review-strategy choices.
