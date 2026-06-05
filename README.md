# QAira Semantic Compiler — Clean Production Fixed

This is the fixed clean-production package.

## Fix included

The previous clean package failed route discovery because `RepositoryIndex.by_kind` missed the `controllers` key.

Fixed:

```text
by_kind.controllers added
RouteDiscoveryAgent guarded with .get()
RouteDiscoveryAgent scans route/controller files first
RouteDiscoveryAgent falls back to all JS/TS files
```

## Architecture

```text
one orchestrator only: src/qaira_semantic_compiler/orchestrator.py
one agent per stage under src/qaira_semantic_compiler/agents/
no version names in output paths
```

## Build

```bash
docker build -t qaira/semantic-compiler:clean-fixed .
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
  qaira/semantic-compiler:clean-fixed
```
