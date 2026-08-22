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
AWS Fargate runs full containers with no runtime limits, so it can clone repositories and perform heavy work. Used as a long-running service it costs money when idle, but paired with AWS Lambda as a trigger it can be run as an on-demand task. Lambda receives the event, spins up a Fargate task for that job, and the task tears itself down when finished. This means paying only for the compute minutes actually used.

## Recommendation
The recommended approach is to consolidate on a single stack, AWS. An AWS Lambda function receives the GitHub webhook event. When heavier work is needed, Lambda spins up an on-demand Fargate task that clones the repository and runs the analysis pipeline, then tears itself down. Keeping the webhook handler and the compute layer on the same platform avoids splitting across two vendors, which simplifies deployment, monitoring, and reasoning about the system.

## How It Connects

1. A pull request is opened on GitHub.
2. GitHub fires a webhook event to our handler's URL.
3. An AWS Lambda function receives the event and validates it.
4. Lambda extracts the key details, such as pull request number, author, and branch.
5. Lambda logs the event. In a later phase, it spins up an on-demand Fargate task for heavier processing.

## Next Steps
1. Set up an AWS Lambda function and deploy a basic handler that receives the webhook and prints it to the console.
2. Register the webhook in the GitHub repository settings, pointing to the Lambda's URL, and subscribe to pull request events.
3. Verify the flow by opening a test pull request and confirming Lambda receives and logs the event.
4. In a later phase, add on-demand Fargate task handoff for cloning and diff analysis.

scklsmdlksmdvlksmdvlksdvsdnm



