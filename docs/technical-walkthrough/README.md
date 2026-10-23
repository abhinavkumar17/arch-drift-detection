# AI-assisted PR review: classification and prompt design

## Purpose and status

The project provides an evidence-based first pass before human PR review. This document covers the classification approach, prompt structure, supporting-code access, and available evaluation records.

The local-only classification policy is agreed for the pilot. Automatic routing remains unintegrated. The approved experimental prompts are not yet connected to the main PR runner. No production-readiness claim is made.

All file links below are repository-relative. The references folder contains frozen source copies for inspection, not a runnable installation or an update to the main implementation. The evidence folder contains selected records from the public synthetic Android fixture. Private presenter notes and account configuration are excluded.

## 1. PR classification

### 1.1 Input and decision

The current advisory classifier examines changed file paths and diff contents. It recognizes narrowly defined translation edits, dependency version updates, and configured release metadata. Unresolved changes fall back to full review.

The pilot will use local rules without an LLM classification call. The existing implementation still supports an optional LLM path; the integrated pilot entry point must enforce the local-only policy.

Branch names, PR titles, and authors are potential additional signals discussed in mentorship. They are not the basis of the current implemented rules.

### 1.2 Implementation and checks

- [Classifier implementation](references/code/classify_pr.py)
- [Classifier behavior and limitations](references/code/CLASSIFICATION.md)
- [Classifier tests](references/code/test_classify_pr.py)

The implementation exposes the classification rules and fallback behavior. Tests exist for the classifier; they were not rerun as part of preparing this document.

### 1.3 Integration boundary

Classification currently produces advice. It does not automatically skip reviews, choose models, or select the main runner's focus prompts. Category-to-action rules remain to be agreed. Small diff size alone does not establish low risk.

## 2. Review instructions and supporting code

### 2.1 Why explicit instructions and a shared base are needed

A diff shows what changed, but it does not contain all the team's engineering expectations. A screen calling a database directly may work correctly while violating the project's rule that data access belongs behind a repository. Explicit review instructions supply that expectation rather than leaving each model to choose its own criteria.

Some instructions apply regardless of the review area: anchor findings to changed lines, provide code evidence, acknowledge missing information, treat source text as data rather than instructions, limit supporting-code investigation, and return a consistent response. These belong in the shared base so they do not have to be repeated and maintained separately in every focus.

The base uses a general review role. An architecture-only role would conflict with correctness and security instructions included in the same review.

- [Frozen base prompt](references/prompts/base.template.md)

### 2.2 Why these three focus areas

The project started with architecture guidelines. Architecture alone does not describe every problem the reviewer should identify: a change can respect the architecture and still produce an incorrect result or expose protected data. We therefore made three distinct review questions explicit:

- **Correctness:** can the change cause incorrect behavior or data handling, including lifecycle and concurrency failures?
- **Security:** can the change allow unauthorized access or expose sensitive data?
- **Architecture:** does the change violate an established responsibility boundary, contract, or state-ownership rule?

These areas reflect the team's mobile-review needs. They are a starting set, not a fixed list for every project. Another domain may need different rules or additional areas. For each PR, the proposed routing would choose from the agreed set rather than redefine the review areas.

Each focus includes scope, examples, reporting criteria, and exceptions. Those boundaries matter: incorrect behavior alone does not prove an architecture violation, and an unfamiliar security-related API does not by itself establish a vulnerability. The reviewer must show the evidence appropriate to the claim.

- [Correctness focus](references/prompts/correctness.md)
- [Security focus](references/prompts/security.md)
- [Architecture focus](references/prompts/architecture.md)

### 2.3 Why separate files, and how they are assembled

The structure contains four prompt files: one shared base and three focuses. A single combined prompt could contain the same guidance. Separating it lets us inspect and refine one area without rewriting the others, and gives us a way to test selecting only relevant instructions.

We did not choose one prompt for every tag or individual rule. Each focus can contain several principles, and several PR categories can use the same focus. A separate tests focus was discussed but deferred for the pilot. Four files represent the agreed pilot scope, not an experimentally proven optimum.

The experimental builder combines the base, selected focuses, build facts, and full annotated diff into one review input. Focus order is fixed, and unknown build facts remain unknown. The model receives the complete diff; related files are not divided among separate reviewers.

Selection could shorten the initial prompt, but it does not guarantee a cheaper or more accurate review. Supporting-code lookups and follow-up requests also consume tokens. Early selection experiments did not establish consistent savings. The highlighted model comparisons included all three focuses rather than automatic selection.

- [Prompt builder](references/prompts/prompt_builder.py)

### 2.4 Repository navigation

The reviewer can find files, search text, and read numbered excerpts from a saved source snapshot. Pi manages the model conversation; the model chooses which tools to request, while the runner restricts access and bounds retrieval.

These capabilities make supporting evidence accessible but do not guarantee that the reviewer reads every relevant file.

- [Repository lookup tools](references/code/repo_tools.mjs)
- [Pi adapter](references/code/pi_repo_review.mjs)

The main-runner adapter shown above is not the exact experimental adapter used for the saved run below. Its retry, compaction, and accounting behavior can differ; the saved run records describe that experiment.

### 2.5 Review trace and evidence

The following saved GLM run provides the initial prompt, lookup requests and returned excerpts, final findings, and request-size and cost records:

- [GLM starting prompt](evidence/prompt.txt)
- [GLM lookup requests and returned excerpts](evidence/events.jsonl)
- [GLM findings and limitations](evidence/findings.json)
- [GLM run summary and cost](evidence/result.json)

A separate local coroutine check established one backend call with shared-request reuse intact and two after reuse was removed. DeepSeek and GPT reported the defect and its cross-screen impact. GLM recognized duplicate calls but left them uncertain. None flagged that behavior in the control.

- [Shared-request runtime evidence](evidence/runtime-results.json)
- [Model comparison metrics](evidence/comparison.csv)

These are constructed-case results. They do not establish production accuracy or prove the cause of every miss.

### 2.6 Improvement criteria

A supervised real-PR pilot should assess useful findings, known misses, false alarms, explanation accuracy, fix quality, completion, and total cost. For a missed issue, inspect supplied and retrieved evidence and request limits before changing instructions or models.

Additional review areas, such as performance or test adequacy, should follow demonstrated team needs. There is no production-traffic evidence yet.
