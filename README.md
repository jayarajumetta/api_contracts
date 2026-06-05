# QAira Semantic Compiler — Field Inference Runtime

Continues from pattern-establishment.

## Fix focus

The last run was stable:

```text
apiContracts        241
bodyDetected        114
bodyFieldsKnown     58
serviceEdges        959
inferredSchemas     58
quality             84.23
```

Remaining weak points:

```text
ServiceBodyPatterns 1
DbWritePatterns     0
```

This package improves:

```text
service call argument capture
service method parameter mapping
body alias propagation
SQL INSERT/UPDATE field extraction
Prisma/Knex/repository object write extraction
false field filtering such as equals/length
```

## Build

```bash
docker build -t qaira/semantic-compiler:field-inference .
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
  qaira/semantic-compiler:field-inference
```
