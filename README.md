# QAira Semantic Compiler — Final Git + LLM Safe Runtime

This package keeps the stable final-compatible contract engine and fixes the two issues from the latest run:

```text
1. git was missing inside Docker
2. malformed quote/escape text in LLM/ReAct-style output should never crash the run
```

## Docker Git fix

The image now installs:

```text
git
ca-certificates
openssh-client
```

So `git clone`, `git commit`, `git push`, and GitHub PR preparation can run when enabled.

## LLM / ReAct safety fix

LLM review now uses strict JSON transport:

```text
json.dumps prompt payload
response_format json_object
safe JSON parsing
markdown/ReAct wrapper extraction
malformed quote/escape fail-open
raw LLM text saved
```

If malformed output occurs:

```text
llm/responses/<agent>.json
llm/raw/<agent>.txt
```

will capture it, and the run continues.

## Build

```bash
docker build -t qaira/semantic-compiler:final-git-safe .
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
  qaira/semantic-compiler:final-git-safe
```

## To actually push and create PR

Your config must explicitly allow it:

```yaml
git_push:
  enabled: true
  execute_git: true
  push: true

pull_request:
  enabled: true
  execute_network_calls: true
```

## Verification files

```text
git/preflight_report.json
git/finalization_report.json
llm/prompts/
llm/responses/
llm/raw/
runtime/final_run_report.json
```
