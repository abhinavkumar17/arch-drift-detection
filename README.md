# arch-drift-detection
Architecture drift detection GitHub Action.

#Architecture Proposal, GitHub Webhook Handler

## Objective
The goal is to build a webhook handler that detects GitHub pull request events. When a new pull request is created, GitHub fires a webhook event to our handler. This is the foundation for a later pipeline that will clone the repository, check out the pull request branch, and analyze the code changes.

This proposal focuses only on steps one and two, receiving and detecting the pull request event. The heavier steps, cloning the repository and annotating the difference, are intentionally deferred and noted in the recommendation.
