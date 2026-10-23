# Building a useful, affordable AI code reviewer

First-pass project story. This document explains the intent and design decisions behind the POC. The existing project README remains the technical reference, and the [research report](../research/README.md) contains the recorded comparison results and limitations.

## How this project started

The starting idea was simple: when a developer opens a PR, could we give the lead a useful first review before they start going through the code?

A lead needs to read the changes, understand the surrounding implementation, and check whether the change follows the team's expectations. We wanted to reduce some of that effort by bringing potential problems—and the evidence behind them—to the reviewer's attention.

Cost mattered too. A review system needs to be affordable enough to use regularly. We didn't want the design to depend on sending every PR to an expensive frontier model. We wanted to find out where lower-cost models could give us useful results and whether a frontier model justified its additional cost.

## Turning our review approach into instructions

We started with architecture because we already had guidelines to work from. Could the reviewer recognize a repository boundary being bypassed or a screen changing state owned by a ViewModel?

As we examined the findings, we expanded the guidance to correctness and security. We needed to explain what each area should check, what evidence would justify a comment, and when it should leave the code alone.

That led to **four prompt files, with different responsibilities**:

| Prompt file | Why it exists |
| --- | --- |
| **Shared base** | Sets the rules for every review: support claims with evidence, anchor comments to changed lines, acknowledge missing context, and return a consistent response. |
| **Correctness** | Checks whether the change can cause incorrect behavior, including lifecycle and concurrency problems. |
| **Security** | Checks for unauthorized access and sensitive-data exposure, with a concrete path to the problem. |
| **Architecture** | Applies the project's rules for boundaries, contracts, and state ownership. |

Keeping the common rules in one base avoids repeating them across every focus. Keeping the focuses separate lets us review and refine each set of instructions without rewriting everything else.

It also gives us a way to investigate cost: a classifier can select the relevant focuses instead of including every section in every review. **That is a savings hypothesis, not a proven result.** Our early comparisons showed that shorter instructions could still lead to more investigation and a higher total cost.

These are not four separate model reviews. The base and selected focuses are assembled into **one review**, with the full diff and access to supporting code. That preserves the opportunity to connect a change in one file to its impact elsewhere. Focus selection has been explored experimentally; the main PR workflow's classifier is still advisory.

## Learning from the results

The early reviews produced useful findings, but finding a suspicious line was only part of the job. Sometimes the model needed to read a related file to establish the impact. Sometimes it identified a real issue but gave a questionable explanation or suggested a fix that changed other behavior.

We therefore compared more than the number of findings. We looked at whether the issue was real, whether the explanation and correction were useful, whether the review finished successfully, and what the complete run cost.

We tried GLM, DeepSeek, GPT, and other candidates to explore that balance. The results did not produce one clear winner: GLM caught an issue that DeepSeek left uncertain, while DeepSeek caught another that GLM did not report as a finding. GPT provided useful frontier-model results, at a higher recorded cost in those comparisons.

The direction is to keep model choice configurable and make cost visible, rather than assume the most expensive model is required for every review. Automatic escalation to a frontier model has not yet been implemented or validated.

## Where we are now

The goal remains a useful, affordable first pass that reduces the lead's review burden. We have demonstrated useful comments on controlled examples, and an earlier local PR-to-comment workflow has been demonstrated.

We still need to connect the newer prompt, classifier, and model decisions to that existing workflow and verify the combined result. We also need to evaluate its usefulness on real changes. The controlled examples do not establish production readiness or prove that reviewers spend less time reviewing.

For the detailed evidence, see the [research findings and model-selection rationale](../research/README.md) and [per-run metrics](../research/shared-request-metrics.csv).
