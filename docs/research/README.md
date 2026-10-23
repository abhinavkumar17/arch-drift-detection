# Local review research: findings and pilot decisions

Status: research snapshot, published for review on 2026-10-22. This is not a production-readiness claim or a completed end-to-end integration.

## What was built and evaluated

We developed a shared review base and three focus sections: correctness, security, and architecture. The base asks for changed-line anchors, code evidence, explicit uncertainty, and structured findings. Tests as a separate focus were deferred.

The experimental runner gives one model the full annotated diff and bounded access to supporting code. Focus selection changes instructions, not which files the reviewer can see. Local experiments recorded prompts, responses, lookups, validation, token usage, and cost. These experiments are separate from the main PR runner.

We tested synthetic, incident-inspired Android changes in public sample code. They are not client code or reproductions of a client's exact incident. They establish behavior on these fixtures, not general accuracy on real PRs.

## Model selection: provisional, not a leaderboard

| Candidate | Observed evidence | Pilot role |
| --- | --- | --- |
| GLM 5.3 Flash | Reported the automatic-retry defect; in the shared-request case noticed duplicate calls but reported only uncertainty | Saved provisional default |
| DeepSeek V4.1 Flash | Left the retry defect uncertain; correctly reported the shared-request defect and both screens' impact | Low-cost alternative; remains a serious candidate |
| GPT 5.6 Terra | Produced accepted findings for both target defects; shared-request fix was appropriate, while retry fix advice was only a partial match to the one-attempt contract | Frontier option |
| Claude Sonnet 4.6 | Useful raw findings were affected by output limits and malformed JSON; a control response was recoverable under acceptance rule v2 | Not in current pilot lineup; this does not establish inferior bug reasoning |

The saved policy names GLM as default, GPT as frontier, and DeepSeek as third option. Later discussions also considered GPT as default; the saved policy was not changed. No automatic fallback or escalation is configured. The deployment default still needs reconciliation during integration.

GLM was retained for promising detection at low observed cost, not because it consistently beat DeepSeek. The later shared-request result explicitly weakens that interpretation. GPT offers a usable frontier comparison in these runs; replacing Claude in the lineup is a practical harness/result decision, not proof GPT is universally better.

Gemini attempts did not yield a completed review because of availability, service, or budget blocks. Llama Maverick's saved attempt did not correctly identify the target retry defect and failed location-side validation. These are limited observations, not rankings.

## Experiment A: automatic retry after API failure

The regression adds unconditional retry for IOExceptions before the error handler. Under persistent failure, one screen action can repeatedly call the API and never reach the failure-state handler. The intended fixture behavior is to surface failure rather than retry indefinitely.

GLM and GPT reported the target mechanism. DeepSeek recognized retries but treated the intended policy as uncertain. Finding detection, explanation accuracy, and fix quality are separate: bounded retry/backoff advice does not fully implement a one-attempt contract.

Acceptance rule v2 removes one enclosing JSON fence only. Saved GLM control output became valid under that rule; original results remain preserved. Claude's malformed quotes remained a failure. GPT required an explicit UTF-8 reader correction, not another model call. Different output caps and sequential harness corrections mean this was not a fully controlled model ranking.

## Experiment B: overlapping requests from two screens

Home and Account intentionally call the same repository. The control reuses the pending request; the regression removes that reuse. A local Kotlin coroutine check showed one API call in the control and two in the regression. This check did not execute Android lifecycle behavior.

Each version was embedded in a larger 17-file fixture retaining four older planted issues. Thus the control is correct only for the new shared-request behavior; it is not an entirely bug-free PR.

All three models received all three focuses, the full diff, and supporting-code lookup access. There was no automatic focus routing. One review per model per version was run.

| Model | Control | Regression target | Cost for both reviews, USD |
| --- | --- | --- | ---: |
| GLM | Four original issues; no shared-request false alarm | Duplicate requests mentioned as a limitation; target missed as a finding | 0.0071112896 |
| DeepSeek | Four original issues; no shared-request false alarm | Found target, explained both screens, suggested restoring pending-request reuse | 0.0060444600 |
| GPT | Four original issues; no shared-request false alarm | Found target, explained both screens, suggested restoring pending-request reuse | 0.1454882000 |

Total recorded cost: $0.1586439496, approximately 15.86 US cents. All six outputs passed structure/location validation, and the assessment recorded detection of all four original issues. Some original-issue explanations and fixes still needed qualification; valid JSON is not proof of correct reasoning.

See [per-run metrics](shared-request-metrics.csv). These are historical run costs, not current pricing or projected production costs. Tokens accumulate across requests. Reasoning tokens are reported separately as recorded and must not be blindly added to output tokens, which can already include them. This extract does not contain cache splits, so it cannot support a cache-normalized price comparison.

## Other research findings

- Small selected-focus comparisons did not establish consistent cost savings. Classifier cost and follow-up investigation must be counted.
- Strict response-wide JSON formatting coincided with skipped lookups and weaker detection in limited tests; causation was not established.
- A final submission tool preserved investigation in some tests but did not show a consistent advantage over normal JSON with validation.
- Normal JSON plus validation remained the experimental baseline. Invalid outputs and failed runs must remain visible; no silent repair should convert them into successes.
- The earlier 33 recorded attempts used older prompt drafts and remain exploratory evidence, not directly comparable with frozen-prompt runs.

## What is and is not integrated

Local scripts exist for PR fetching, review, preview, and publishing. However, at publication:
- The main PR runner still defaults to Claude.
- Classification is advisory and proposes focuses; it does not automatically route reviews.
- Classifier changes and review modifications remain uncommitted locally.
- Approved experimental prompts and model policy are not fully wired into one verified end-to-end command.
- No production deployment or automatic frontier fallback is claimed.

The next engineering step is to connect the agreed configuration to the existing PR workflow and verify it end to end. Further synthetic model exploration is paused. For stronger evidence, replay a real historical PR from before a substantive human correction, withholding the later comments and fix from the reviewer. No such real-PR case has been selected or validated yet.

## Evidence provenance and publication boundary

This summary was checked against local artifacts:
- pilot-model-policy.json
- shared-request-01/comparison.csv and assessment.json
- shared-request-01/runtime-results.json
- acceptance-v2-results.json
- retry-models-01/results.json
- gpt-review-01/gpt-regression-1-plain/result.json and findings.json

These source artifacts remain in the local experiment archive, not linked as publicly accessible files. The per-run CSV is a curated numeric extract from that archive. Qualitative assessments are human judgments and should be reviewed, not treated as independent ground truth.

This publication includes documentation and curated metrics only. It excludes credentials, account configuration, raw provider traffic, local absolute paths, and full source snapshots. It does not change executable behavior or run new paid reviews. Public/synthetic-code results do not authorize client-code processing; provider/data-policy approval remains a separate prerequisite.
