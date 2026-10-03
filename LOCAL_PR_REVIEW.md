# Run the local PR review

The coordinator and publisher are included in this repository. They support public GitHub
test repositories; private-repository and unattended cloud authentication remain pending.

Install Python 3.10 or newer, Git, GitHub CLI, Docker, Node.js and Pi. Authenticate GitHub CLI
for the repository you are reviewing, configure OpenRouter access for Pi, and build the Docker
preparation image as described in the main README. Install the Python diff parser with
`python -m pip install unidiff`.

Start by fetching the PR without calling a model:

```shell
python review_pr.py --pr https://github.com/OWNER/REPOSITORY/pull/NUMBER --prepare-only
```

Run a review (this makes paid model calls):

```shell
python review_pr.py --pr https://github.com/OWNER/REPOSITORY/pull/NUMBER --provider openrouter --model YOUR_OPENROUTER_MODEL
```

The coordinator prints the saved run folder. Use that folder to preview a GitHub review:

```shell
python publish_review.py --run PATH_TO_RUN_FOLDER
```

Inspect `review-to-post.json` in that folder before explicitly submitting:

```shell
python publish_review.py --run PATH_TO_RUN_FOLDER --post
```

Fetching and publishing check that PR revisions still match. Posting remains a separate,
explicit step. Format and line checks do not establish that a model's finding is correct.
Offline tests cover posting guards; repeated live posting still needs verification.

For offline verification, install `pytest` and `unidiff`, then run:

```shell
python -m pytest host_tests/test_review_pr.py host_tests/test_publish_review.py host_tests/test_response_format.py host_tests/test_provider_policy.py host_tests/test_review_local.py host_tests/test_repo_context.py
node --test lambda/index.test.mjs
```

The Lambda remains a separate intake prototype. See [webhook configuration](lambda/README.md).
