# QAira Semantic Compiler — Clean Production Runtime

This package intentionally has **one orchestrator only**:

```text
src/qaira_semantic_compiler/orchestrator.py
```

Every stage is a separate agent file:

```text
agents/source_detection_agent.py
agents/route_discovery_agent.py
agents/body_discovery_agent.py
agents/params_discovery_agent.py
agents/param_type_discovery_agent.py
agents/validation_schema_agent.py
agents/import_graph_agent.py
agents/service_graph_agent.py
agents/schema_attachment_agent.py
agents/response_discovery_agent.py
agents/contract_builder_agent.py
agents/relationship_agent.py
agents/test_generation_agent.py
agents/quality_gate_agent.py
agents/llm_gateway_agent.py
agents/artifact_manifest_agent.py
```

Generated output files do not include release/version names.

## Build

```bash
docker build -t qaira/semantic-compiler:clean .
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
  qaira/semantic-compiler:clean
```
