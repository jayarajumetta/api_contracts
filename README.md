# QAira Semantic Compiler Platform V63 — Accuracy Restore

V63 is based on the stable V61 runtime, not the V62 no-hang branch.

## What V63 fixes

Your V61 run completed, but accuracy regressed:

```text
bodyDetected: 1 / 123
bodyDetectionRate: 0.81%
```

Root cause:

```text
old regex parser stopped at async (req, reply)
rawHandler became only "async (req"
```

V63 replaces the old route regex with a balanced parenthesis route-call scanner.

## Expected result

The route handler body should no longer truncate at `async (req`.

You should see parser type:

```text
regex-balanced-v63
```

in:

```text
/output/ast/parser_capability_report.json
/output/diagnostics/body_detection_detail.json
```

## Build

```bash
docker build -t qaira/semantic-compiler:v63 .
```

## Run

```bash
docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -v /Users/jayarajumetta/MJ/qaira:/repo:ro \
  -v /Users/jayarajumetta/Downloads/volume/output:/output \
  -v /Users/jayarajumetta/Downloads/volume/config.yaml:/config/config.yaml:ro \
  -v /Users/jayarajumetta/Downloads/volume/learning:/learning \
  qaira/semantic-compiler:v63
```
