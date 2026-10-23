# Building a useful, affordable AI code reviewer

## 1. Why we started

When a developer raises a PR, a lead needs to read the changes, understand the surrounding code, and check whether the implementation follows the team's expectations.

We wanted to give the lead a useful first pass before that review: possible problems, the code that supports each finding, and an explanation of what could go wrong. The lead still decides whether the finding is valid.

Cost was part of the idea from the beginning. We wanted a system we could use regularly, without depending on an expensive frontier model for every change.

## 2. Does every PR need an AI review?

Before sending a PR to a model, we want to ask whether it needs that review at all.

For example, a PR that only updates translated text may not need the same review as a change to login behavior. If we can reliably recognize routine changes, we may be able to avoid unnecessary model calls.

That is the proposed job of the classifier. **How it should make that decision is still open:**

- **Local checks:** use code to inspect the files and changes against agreed rules. This adds no LLM token cost, but the rules will only cover cases we have defined.
- **LLM classification:** ask a model to assess the change. This adds cost and can make mistakes, so we need to establish whether it avoids enough review work to be worthwhile.
- **A combination:** use local checks first and ask a model only when those checks cannot decide.

The cost question is simple: **does classification cost less than the reviews it helps us avoid?** We need to compare the full cost of classification plus the remaining reviews against reviewing every PR. We also need to check that the savings do not come from skipping changes that needed attention.

We have not set an acceptable classifier-call budget or approved automatic skipping. For now, an uncertain decision should lead to review. A small diff alone is not a reason to skip it.

*Current status: local classification rules exist, but they are advisory. They do not automatically skip reviews.*

## 3. If the PR needs review, what should we ask the model to check?

We could send the diff directly to a model and say, "Review this." But the diff tells it what changed—not all the expectations our team has for that code.

For example, a screen calling the database directly might work, but violate our rule that data access goes through a repository. The reviewer needs that rule to explain why the change is a problem.

We therefore made our review expectations explicit in three areas:

- **Correctness:** can this change make the app behave incorrectly?
- **Security:** can it allow unauthorized access or expose sensitive data?
- **Architecture:** does it break the project's rules about responsibilities, boundaries, or ownership?

We chose correctness, security, and architecture as our starting review areas because they reflect how we review mobile applications. They are not a fixed list for every project. We can adjust the rules or add other areas based on the project's domain and the team's needs.

For each PR, we then choose the relevant instructions from that agreed set.

A **shared base** holds the rules that apply to all three: show evidence, point to the changed line, and say when information is missing.

That gives us four prompt files: one base and three focuses. Keeping them separate lets us refine each area and potentially select only the instructions relevant to a PR. They are combined for one review; we do not split related files between different reviewers.

Selecting fewer sections might reduce the starting prompt, but it does not guarantee a cheaper review. The model may still spend more on supporting-code lookups and follow-up requests. Our early experiments did not establish consistent savings.

So these are two different decisions: **first, whether to run an AI review; then, which review instructions to include.**

*Current status: automatic selection of these instructions is not yet connected to the main PR review command.*

## 4. Preparing the code for review

Once we decide to review a PR, we need to prepare the changes so the model can read them and return comments we can place on GitHub.

First, we fetch the versions of the code being compared. This gives the review a fixed starting point. If someone updates the PR afterward, we need to know that before posting an older review.

Next, we label the diff: which lines were added, which were removed, and which are surrounding context. We also record the locations where comments are allowed. This lets us check that a finding points to a valid changed line rather than an unrelated part of the file.

We then combine the diff with the review instructions and estimate the size of the complete request. If it exceeds the configured input limit, preparation stops before calling the model. We do not silently remove files to make it fit, because that could hide information needed to understand the change.

This size check helps control what we send, but it is not a complete spending limit. The model may request more code during the review, and its response also uses tokens.

We keep a source snapshot available for those requests. The model receives the diff first and can inspect supporting code when it needs to understand an interface, implementation, or caller.

*Current status: this preparation exists. The main workflow still uses its older instruction assembly; connecting the newer shared base and focus files remains integration work.*

## 5. Running the review with Pi

A review does not always finish with one request and one answer. The model may need to ask, "Where is this interface implemented?" or "How does the other screen use this function?"

We chose Pi to handle that conversation instead of building the conversation and tool-call handling ourselves.

Our runner sends the prepared review to the selected model through Pi. If the model requests supporting code, our read-only tools can find files, search text, or return relevant lines. That code becomes part of the next request, and the review continues.

The responsibilities are separate:

- **Our runner** supplies the instructions, source access, limits, and output checks.
- **Pi** manages the conversation with the model and its tool calls.
- **OpenRouter** provides access to the selected model.

These additional requests matter for cost. A shorter starting prompt does not necessarily mean a cheaper review: the model may investigate more files or produce a longer answer. We therefore need to measure the whole review, not just its first request. The runner also checks the estimated input size again as supporting code is added.

When the model finishes, we validate the response structure and comment locations, then save the result for inspection. These checks make the response usable; they do not prove that its reasoning is correct. Posting the findings to GitHub is a separate, explicit step.

*Current status: reviews with supporting-code lookups have been demonstrated. The newer classifier, prompt selection, and model policy still need to be connected and verified together in the main workflow.*

## 6. What happened when we ran the reviews?

Once we had the review instructions and supporting-code tools, we wanted to answer a practical question: **could a lower-cost model give us useful findings, or did we need a frontier model?**

We used saved Android changes and ran them through GLM, DeepSeek, and GPT. For these comparisons, we included the shared base and all three focus sections. We did not use classification to choose different instructions: we wanted to compare the models without also changing what they were asked to check.

Each model received the full diff and could inspect supporting files. These were controlled examples, not live production PRs.

### First: repeated API calls after a failure

We introduced a change that retries an API call whenever it throws an IOException. Under persistent failure, it keeps calling the API instead of reaching the code that shows the failure state.

We asked the models to review the change without telling them the expected finding.

| Model | What came back | Recorded cost for the broken-version review |
| --- | --- | ---: |
| GLM | Reported the repeated retries as an issue. | $0.00296 |
| DeepSeek | Noticed the retries but treated the intended behavior as uncertain. | $0.00222 |
| GPT | Reported the repeated retries as an issue. | $0.07061 |

GLM showed that a cheaper model could identify this problem. However, detecting the issue did not make every suggested fix correct: advice to add limited retries or backoff did not fully match our intended behavior of showing failure after one attempt.

These runs also had different output allowances—GPT had a larger allowance—and acceptance handling evolved during the experiments. They are useful observations, not a tightly controlled ranking.

### Next: a change affecting two screens

We then checked whether the reviewer could connect a repository change to its callers.

Home and Account both request the same data. The working version shares an ongoing request. The broken version starts another request instead of sharing it. A local coroutine test confirmed **one backend call in the working version and two in the broken version**.

Each model reviewed both versions. This let us check whether it caught the defect and whether it incorrectly complained when sharing worked.

| Model | Broken-version result | False alarm about sharing in the working version? | Recorded cost for both reviews |
| --- | --- | --- | ---: |
| GLM | Noticed duplicate calls but left them as uncertainty. | No | $0.00711 |
| DeepSeek | Reported the defect, connected both screens, and suggested restoring request sharing. | No | $0.00604 |
| GPT | Reported the defect, connected both screens, and suggested restoring request sharing. | No | $0.14549 |

Both versions were part of a 17-file fixture containing four older planted issues. "Working" refers only to the request-sharing behavior, not to the entire change being free of bugs.

### What we took from these results

The second example changed the picture from the first. GLM did well on retries, but DeepSeek did better on shared requests. GPT reported both target issues, at a substantially higher recorded cost.

That supports keeping lower-cost models in consideration. It does not support declaring GLM or DeepSeek the permanent winner. Our saved pilot policy therefore remains provisional: GLM as the default candidate, DeepSeek as another low-cost option, and GPT as the frontier option. Automatic switching between them is not implemented.

The costs above are in USD and include each listed review's follow-up requests. They do not include every earlier failed attempt or the total research spend. The first table covers one review per model; the second covers two.

These examples show useful findings and concrete trade-offs. They do not yet establish production accuracy or savings from classification. The next evidence should come from real PRs rather than more planted examples.

[Supporting research report](../research/README.md) · [Shared-request per-run metrics](../research/shared-request-metrics.csv)
