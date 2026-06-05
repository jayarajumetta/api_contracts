# QAira Semantic Compiler — Self-Healing Docs Git Sync

This patch keeps the self-healing/docs engine unchanged and fixes the Git non-fast-forward push issue.

## Problem from latest run

```text
develop -> develop rejected: non-fast-forward
```

Reason: local `develop` was created from `main`, while remote `develop` already had commits.

## Fix

Branch sync now works like this:

```text
git clone
git fetch origin --prune
if origin/develop exists:
    checkout -B develop origin/develop
else:
    checkout main
    checkout -B develop
commit generated artifacts
git push develop:develop
```

So normal push should work without force.

## Build

```bash
docker build -t qaira/semantic-compiler:self-healing-docs-git-sync .
```

## Run

```bash
docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e GIT_USERNAME="$GIT_USERNAME" \
  -e GIT_TOKEN="$GIT_TOKEN" \
  -v /Users/jayarajumetta/MJ/qaira:/repo:ro \
  -v /Users/jayarajumetta/Downloads/volume/output:/output \
  -v /Users/jayarajumetta/Downloads/volume/config.yaml:/config/config.yaml:ro \
  -v /Users/jayarajumetta/Downloads/volume/learning:/learning \
  qaira/semantic-compiler:self-healing-docs-git-sync
```
