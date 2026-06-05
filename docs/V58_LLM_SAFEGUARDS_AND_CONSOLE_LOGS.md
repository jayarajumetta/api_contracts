# V58 LLM Safeguards + Console Logs

## LLM behavior

LLM is enabled in config but fail-open:

```text
LLM timeout/error/missing key
↓
record prompt/report
↓
continue deterministic execution
↓
finish output
```

## Console logs

```text
[Qaira][START] stage
[Qaira][END] stage
[Qaira][LLM-SKIP] stage
[Qaira][LLM-FAIL-OPEN] stage
```

## Recommended Docker

```bash
docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -v /Users/jayarajumetta/MJ/qaira:/repo:ro \
  -v /Users/jayarajumetta/Downloads/volume/output:/output \
  -v /Users/jayarajumetta/Downloads/volume/config.yaml:/config/config.yaml:ro \
  -v /Users/jayarajumetta/Downloads/volume/learning:/learning \
  qaira/semantic-compiler:v58
```
