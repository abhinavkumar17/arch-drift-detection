# Building a useful, affordable AI code reviewer

## Why we started

The starting idea was simple: when a developer opens a PR, could we give the lead a useful first review before they start going through the code?

A lead needs to read the changes, understand the surrounding implementation, and check whether the change follows the team's expectations. We wanted to reduce some of that effort by bringing potential problems—and the evidence behind them—to the reviewer's attention.

Cost mattered too. The system needs to be affordable enough to use regularly. We didn't want every PR to depend on an expensive frontier model. We wanted to understand where lower-cost models could produce useful reviews and when a frontier model justified its additional cost.

We started with architecture because we already had guidelines to work from. Could the reviewer recognize a repository boundary being bypassed or a screen changing state owned by a ViewModel?

The early results were useful, but detecting a suspicious line wasn't enough. Some findings needed supporting code to establish their impact. Others identified a real problem but gave an inaccurate explanation or an incomplete fix. Those results shaped both the review instructions and how we evaluated the output.

## Why we use four prompt files

As we expanded the review to correctness and security, we separated the instructions into four files:

| Prompt file | Responsibility |
| --- | --- |
| **Shared base** | Rules for every review: require evidence, anchor comments to changed lines, acknowledge missing context, and return a consistent response. |
| **Correctness** | Check whether the change can cause incorrect behavior, including lifecycle and concurrency problems. |
| **Security** | Check for unauthorized access or sensitive-data exposure, supported by a concrete path to the problem. |
| **Architecture** | Apply the project's rules for boundaries, contracts, and state ownership. |

The base keeps common rules consistent. Separate focus files let us refine one area without rewriting the others. Each focus explains what to avoid, what to prefer, what justifies a comment, and which exceptions should prevent false alarms.

This structure also lets us explore selecting only the relevant instructions for a PR. A classifier proposes the focuses; uncertain classification falls back to a full review. **Whether selection saves money remains an open question.** In our early comparisons, shorter instructions sometimes led to more investigation and a higher total cost.

These files do not create four separate model reviews. The base and chosen focuses are assembled into one review. The model receives the full diff and can inspect supporting code, so it can connect changes across files.

## How one PR moves through the system

Imagine a PR changes a repository used by both Home and Account. The change is in one place, but its effect may reach both screens.

**1. Prepare the change.**

We give the local runner a GitHub PR link. It fetches the revisions, prepares the diff, marks which changed lines can receive comments, and makes a source snapshot available for investigation. This preparation already exists.

**2. Select the review guidance.**

The classifier proposes relevant focus areas. The intended integration combines those focuses with the shared base. The classifier exists locally, but its suggestions do not yet automatically select prompts in the main PR command.

**3. Let one model investigate.**

The model receives the instructions and full diff. If it needs to understand how Home and Account use the repository, it can request related files through limited, read-only tools.

Pi manages the conversation and tool calls. Our runner supplies the instructions, code access, and limits. OpenRouter provides access to the selected model. We have demonstrated this investigation flow; the newer prompt files and model policy still need connecting to the main command.

**4. Validate and save the result.**

The runner checks the response structure and comment locations, then saves the findings and run records. These checks establish that the output can be processed; they do not establish that the finding is correct. A developer still assesses its explanation and proposed fix. Our experiments also recorded token usage and cost.

**5. Preview and publish.**

The publisher prepares the GitHub comments for inspection. Posting is a separate, explicit action, with checks for changed PR revisions and an already-posted matching review. An earlier local run successfully posted a finding on the correct PR line.

## What the experiments taught us

We compared models on detection, explanation accuracy, fix quality, completion, and cost—not just the number of comments.

The results did not produce one clear winner. GLM reported the automatic-retry issue that DeepSeek left uncertain. In the overlapping-request scenario, DeepSeek and GPT reported the defect and its impact on both screens, while GLM described duplicate calls as a limitation rather than a finding.

GPT produced useful frontier-model results, at a higher recorded cost in these comparisons. Claude produced useful raw findings too, but output-limit and formatting failures affected whether those results could be accepted. That is a reliability observation about these runs, not proof that Claude cannot review the code.

Our direction is to keep model choice configurable and cost visible. The saved pilot policy lists GLM as the provisional default, GPT as the frontier option, and DeepSeek as another low-cost option. This policy is not yet wired into the main runner. Automatic escalation to a frontier model has not been implemented or validated.

The detailed findings and costs remain in the separate [research report](../research/README.md) and [per-run metrics](../research/shared-request-metrics.csv).

## Where we are now

We have demonstrated an earlier local PR-to-comment workflow and useful findings on controlled examples. We also have newer prompts, classification work, and model comparisons saved locally.

The next step is to connect those newer decisions to the existing workflow and verify the combined result. We then want to assess it on a real historical PR, using the version before a substantive human correction and withholding the later review comments and fix from the model.

The goal remains a useful, affordable first pass that reduces the lead's workload. The experiments support continuing the POC; they do not yet prove production readiness or a reduction in review time. Webhooks and cloud deployment can follow once the integrated local flow is working.
