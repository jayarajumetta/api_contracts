# QAira Semantic Compiler — Contract Quality Cleanup

Continues from precision-field baseline.

## What this release changes

No changes to stable discovery/propagation logic.

Cleanup only:

```text
declaredSchemaAttachments separated from inferredSchemaAttachments
OpenAPI uses components.schemas for inferred request schemas
Required field confidence added
Negative Postman tests generated
Edge Postman tests generated
Summary metric names cleaned
```

## Build

```bash
docker build -t qaira/semantic-compiler:contract-quality .
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
  qaira/semantic-compiler:contract-quality
```

## Expected

```text
bodyDetected around 118
bodyFieldsKnown around 99
declaredSchemaAttachments may be low
inferredSchemaAttachments around 99
negative tests > 0
edge tests > 0
OpenAPI components.schemas populated
```
