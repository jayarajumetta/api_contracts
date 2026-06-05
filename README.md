# QAira Semantic Compiler — Final Config-Safe Enterprise Loop

This package makes config override optional.

## Key change

The agent now runs even if you do **not** mount:

```text
/config/config.yaml
```

It uses the bundled config:

```text
/app/config/config.example.yaml
```

If you do mount a config, it becomes a **deep-merge override**, not a full replacement.

## External-input features default OFF

These are false by default:

```text
llm_review.enabled
llm_review.execute_network_calls
git_push.enabled
git_push.execute_git
git_push.push
git_finalization.enabled
git_finalization.execute_git
git_finalization.push
pull_request.enabled
pull_request.execute_network_calls
```

So the default run performs:

```text
source scan
agent iteration
contract generation
test generation
quality gate
artifact manifest
LLM prompt/context saving only if enabled by override
no real LLM call
no git push
no PR
```

## Run without config override

```bash
docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -v /Users/jayarajumetta/MJ/qaira:/repo:ro \
  -v /Users/jayarajumetta/Downloads/volume/output:/output \
  -v /Users/jayarajumetta/Downloads/volume/learning:/learning \
  qaira/semantic-compiler:config-safe
```

## Run with optional config override

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
  qaira/semantic-compiler:config-safe
```

## To enable external integrations

Add only what you need in the override config:

```yaml
llm_review:
  enabled: true
  execute_network_calls: true

git_push:
  enabled: true
  execute_git: true
  repo_url: "https://github.com/jayarajumetta/api_contracts.git"
  target_branch: develop
  push: true

pull_request:
  enabled: true
  execute_network_calls: true
  base_branch: main
```

## Verification

```text
config/effective_config.json
runtime/config_compatibility_report.json
runtime/iteration_context.json
summary/scan_summary.json
quality/quality_gate_report.json
```
