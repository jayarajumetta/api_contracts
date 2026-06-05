# QAira Semantic Compiler — Final Git Diagnostics Runtime

This patch keeps the stable contract engine unchanged and improves Git finalization diagnostics.

## Why

Latest run showed:

```text
git installed ✅
commit created ✅
push failed ❌ exit 128
stderr not captured ❌
```

This package captures the exact reason.

## Improvements

```text
git command stdout/stderr captured
git/command_log.json added
push uses git -c http.extraHeader=Authorization: Bearer <token>
avoids token-in-URL escaping issues
push uses -u origin <branch>
PR body_file supported
likely push cause classified
```

## Build

```bash
docker build -t qaira/semantic-compiler:final-git-diagnostics .
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
  qaira/semantic-compiler:final-git-diagnostics
```

## Check after run

```text
git/finalization_report.json
git/command_log.json
git/preflight_report.json
```
