# Webhook intake prototype

Set `GITHUB_WEBHOOK_SECRET` to the same secret configured on the GitHub webhook.
Set `ALLOWED_REPO` to the repository being reviewed, in `owner/name` format.
Missing configuration rejects requests. Do not commit secret values.

The handler verifies the SHA-256 signature over the original request bytes before parsing JSON.
The gateway must preserve the raw body (base64-encoded Lambda bodies are supported).
Only `pull_request` events with `opened`, `synchronize`, or `reopened` actions are accepted.
Only repository and PR identifiers are logged; no token is included in the packet.

This is an intake prototype, not a deployed review service. It does not start Fargate tasks,
call models, or post comments. Delivery deduplication and downstream dispatch remain pending.

Run the offline checks with `node --test lambda/index.test.mjs`.
