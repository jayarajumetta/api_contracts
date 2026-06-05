# QAira Semantic Compiler — Final Compatible Auto-Iterative Runtime

This is the final package built for your current config style.

It preserves the stable `contract-quality` baseline and wires the same interactive loop we followed manually:

```text
run agents
analyze results
rank top issues
save / optionally call LLM review
apply known deterministic remediation
run again
preserve best iteration
finalize artifacts
optionally git commit / push / PR
```

## One orchestrator only

```text
src/qaira_semantic_compiler/orchestrator.py
```

## Supported config styles

This package accepts both:

```text
auto_iteration + git_finalization + llm_review
```

and your current uploaded style:

```text
agentic_runtime + git_push + llm
```

A compatibility report is written here:

```text
runtime/config_compatibility_report.json
```

## Important Git / PR behavior

Your uploaded config had:

```yaml
git_push:
  enabled: true
  execute_git: true
  push: false
```

That means the agent may clone/commit locally inside the container, but it will not push unless:

```yaml
git_push:
  push: true
```

For GitHub PR creation you must also set:

```yaml
pull_request:
  enabled: true
  execute_network_calls: true
```

## LLM behavior

Your uploaded config had LLM enabled, but this package keeps actual network calls off by default for safety.

To allow actual LLM calls:

```yaml
llm_review:
  execute_network_calls: true
```

or add this compatible section:

```yaml
llm_review:
  enabled: true
  execute_network_calls: true
```

## Build

```bash
docker build -t qaira/semantic-compiler:final .
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
  qaira/semantic-compiler:final
```

## Key outputs

```text
summary/scan_summary.json
quality/quality_gate_report.json
analysis/results_analysis.json
analysis/remediation_report.json
iterations/iteration_*/...
runtime/best_iteration.json
runtime/final_run_report.json
runtime/config_compatibility_report.json
git/finalization_report.json
llm/prompts/*.json
llm/responses/*.json
```
