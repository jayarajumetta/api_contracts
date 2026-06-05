# QAira Semantic Compiler Platform V58 — LLM Safe-Guarded Runtime

V58 is built on V57 and adds the operational safeguards you asked for:

```text
LLM enabled in config
selective LLM only
short timeout
single retry
fail-open behavior
continue deterministic agents if LLM fails
console logs at every major stage
heartbeat logs
scan folder exclusions
clear final outcome artifacts
```

## What changes in V58

### LLM is enabled but safe

```yaml
llm:
  enabled: true
  timeout_seconds: 20
  max_retries: 1
  fail_open: true

llm_invocation:
  enabled: true
  mode: selective
  continue_on_timeout: true
  continue_on_error: true
  max_stage_llm_calls_per_iteration: 8
```

If LLM fails:

```text
record failure
write prompt/diagnostic
continue deterministic execution
finish output
```

### Console logs are forced

Run with:

```bash
-e PYTHONUNBUFFERED=1
```

V58 prints:

```text
[Qaira][START] stage
[Qaira][END] stage
[Qaira][LLM-SKIP]
[Qaira][LLM-FAIL-OPEN]
[Qaira][DONE]
```

### Scan exclusions

V58 skips heavy folders:

```text
node_modules
.git
dist
build
coverage
.next
.cache
playwright-report
test-results
```

## Docker Run

```bash
docker build -t qaira/semantic-compiler:v58 .

docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -v /Users/jayarajumetta/MJ/qaira:/repo:ro \
  -v /Users/jayarajumetta/Downloads/volume/output:/output \
  -v /Users/jayarajumetta/Downloads/volume/config.yaml:/config/config.yaml:ro \
  -v /Users/jayarajumetta/Downloads/volume/learning:/learning \
  qaira/semantic-compiler:v58
```

## Live log

```bash
tail -f /Users/jayarajumetta/Downloads/volume/output/verbose/agent_stage_log.jsonl
```

## Important outputs

```text
/output/runtime/confidence_report.json
/output/runtime/selective_llm_invocation_report.json
/output/llm/selective_prompts/
/output/llm/fail_open_report.json
/output/verbose/console_progress.log
/output/summary/scan_summary.json
```
