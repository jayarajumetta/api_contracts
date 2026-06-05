# QAira Semantic Compiler — Pattern Establishment Runtime

Continues from clean-enhanced.

## Added pattern establishment agents

```text
ServiceBodyFieldAgent
DbWriteFieldAgent
ServiceBodyPropagationAgent
InferredSchemaRegistryAgent
```

## Purpose

Move from:

```text
body detected but fields unknown
```

to:

```text
fields inferred from service usage and DB write patterns
```

Expected improvement:

```text
bodyFieldsKnown increases
inferredSchemas increases
schemaAttachments increases
OpenAPI request body fields improve
```

## Build

```bash
docker build -t qaira/semantic-compiler:patterns .
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
  qaira/semantic-compiler:patterns
```
