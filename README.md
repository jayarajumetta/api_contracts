# QAira Semantic Compiler — Final Config-Safe Git Routing Fix

This patch fixes the issue seen in the latest run:

```text
git_push.enabled=true
git_finalization.enabled=false
```

The old selector picked `git_finalization` first and disabled Git, even though `git_push` was enabled.

## Fixed behavior

Config priority is now:

```text
1. git_push if git_push.enabled=true
2. git_finalization if git_finalization.enabled=true
3. git if git.enabled=true
4. disabled
```

## LLM 429 fix

`ResultsAnalyzerAgent` no longer calls LLM directly.

Only this agent can call LLM:

```text
IterationLLMReviewerAgent
```

and it uses:

```text
runtime/iteration_context.json
```

with call budget control.

## Build

```bash
docker build -t qaira/semantic-compiler:config-safe-gitfix .
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
  qaira/semantic-compiler:config-safe-gitfix
```

## Verify

```text
git/finalization_report.json
git/command_log.json
analysis/results_analysis.json
analysis/iteration_llm_review.json
```
