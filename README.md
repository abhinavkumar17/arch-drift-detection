# arch-drift-detection
Architecture drift detection GitHub Action.

## Architecture Proposal, GitHub Webhook Handler

## Objective
The goal is to build a webhook handler that detects GitHub pull request events. When a new pull request is created, GitHub fires a webhook event to our handler. This is the foundation for a later pipeline that will clone the repository, check out the pull request branch, and analyze the code changes.

This proposal focuses only on steps one and two, receiving and detecting the pull request event. The heavier steps, cloning the repository and annotating the difference, are intentionally deferred and noted in the recommendation.

## The Two Options

### Option One, Cloudflare Workers
Cloudflare Workers is a lightweight serverless platform that runs small pieces of code instantly when triggered. It scales to zero, meaning you pay nothing when idle, and it offers a genuinely free tier of one hundred thousand requests per day. It is ideal for receiving a webhook and reacting quickly. Its limitation is a constrained runtime and short execution time, so it cannot clone large repositories in process.

### Option Two, AWS Fargate
AWS Fargate runs full containers with no runtime limits, so it can clone repositories and perform heavy work. It is powerful and flexible. The trade-offs are a heavier setup, and it does not scale to zero, meaning it costs money even when idle. It also requires more AWS configuration and a billing setup.


1. A pull request is opened on GitHub.

## Recommendation
Receiving and detecting pull request events, Cloudflare Workers is the recommended choice. The task is lightweight, event-driven, and short-lived, which matches exactly what Workers is built for. It requires no billing setup, scales to zero, and can be deployed quickly on a free account.

Looking ahead, the heavier steps, cloning the repository and analyzing the diff, exceed what Cloudflare Workers can handle in process. Rather than forcing everything onto one platform, the proposed architecture splits the work. The Cloudflare Worker receives the webhook and places a job on a queue. A separate container, such as AWS Fargate triggered by that queue, performs the heavy cloning and analysis later. This keeps the fast path cheap and simple, while reserving heavier infrastructure only for when it is actually needed.

## How It Connects

1. A pull request is opened on GitHub.
2. GitHub fires a webhook event to our handler's URL
3. The Cloudflare Worker receives the event and validates it.
4. The Worker extracts the key details, such as pull request number, author, and branch.
5. For this week, the Worker logs or acknowledges the event. In a later phase, it will place a job on a queue for heavier processing.

## Next Steps
1. Set up a Cloudflare Worker and deploy a basic handler that receives requests.
2. Register the webhook in the GitHub repository settings, pointing to the Worker's URL, and subscribe to pull request events.
3. Verify the end-to-end flow by opening a test pull request and confirming the Worker receives and logs the event.
4. In a later phase, add queue-based handoff to a heavier container for cloning and diff analysis.
