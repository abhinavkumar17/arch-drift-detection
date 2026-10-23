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
