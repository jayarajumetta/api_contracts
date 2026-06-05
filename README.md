# QAira Semantic Compiler — Clean Production Enhanced

This enhanced clean package fixes the body-count regression found in the clean-fixed run.

## Fixes

```text
Route discovery works: 241 routes
Service graph works: 959 edges
BodyDiscovery now marks req.body presence even when exact fields are unknown
QualityGate counts bodyDetected from body presence, not only known fields
OpenAPI requestBody generated for unknown object bodies
Schema discovery scans all source files for schema-like declarations
Schema attachment enriches requestBody with schemaRef when possible
```

## Architecture

```text
one orchestrator only
one agent per stage
no version names in output paths
shared repository index
balanced route parser
fail-open runtime
```

## Build

```bash
docker build -t qaira/semantic-compiler:clean-enhanced .
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
  qaira/semantic-compiler:clean-enhanced
```
