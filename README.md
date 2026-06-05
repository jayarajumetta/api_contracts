# QAira Semantic Compiler — Final Git Auth Runtime

This patch fixes the latest Git clone failure:

```text
fatal: could not read Username for 'https://github.com'
```

## Root cause

`http.extraHeader=Authorization: Bearer ...` was not reliable for `git clone` in this environment.

## Fix

GitHub standard token-auth URL is now used:

```text
https://x-access-token:<TOKEN>@github.com/org/repo.git
```

The token is URL-encoded and redacted from all logs.

## Build

```bash
docker build -t qaira/semantic-compiler:final-git-auth .
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
  qaira/semantic-compiler:final-git-auth
```

## Verify

```text
git/finalization_report.json
git/command_log.json
runtime/final_run_report.json
```

If this still fails, `likelyCause` will tell whether it is:

```text
invalid token
missing repo access
no write permission
protected branch
repo not found
```
