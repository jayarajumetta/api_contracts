# QAira Semantic Compiler — Precision Field Inference

This package fixes over-propagation from the field-inference run.

## Problem fixed

Previous run found strong patterns but over-counted:

```text
bodyExpected        123
bodyFieldsKnown     210
bodyFieldKnownRate  170%
```

That is impossible.

## Corrections

```text
DB write fields scoped to called service method only
No requestBody added to GET/DELETE unless req.body is explicitly used
Inferred schemas only for POST/PUT/PATCH or confirmed body routes
Quality rates capped at 100%
bodyFieldsKnown counted only across body-expected routes
```

## Build

```bash
docker build -t qaira/semantic-compiler:precision-fields .
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
  qaira/semantic-compiler:precision-fields
```
