# QAira Semantic Compiler — Self-Healing + Premium Docs Runtime

This version extends the successful baseline with:

```text
AgentPerformanceEvaluatorAgent
SelfHealingLLMAdvisorAgent
SelfHealingCodeDeltaAgent
ApiDocumentationAgent
Enhanced TestGenerationAgent
```

## Self-healing design

Each run now produces:

```text
self_healing/agent_performance_report.json
self_healing/llm_advice.json
self_healing/code_delta_report.json
codegen/agent_deltas/*.patch_plan.json
```

Workflow:

```text
each agent runs
performance evaluator scores each agent
one compact LLM advisor call, only if weak agent or score below threshold
LLM suggestions are mapped to agent-specific delta plans
safe patch plans generated
optional future deterministic patch application
final artifacts pushed after quality is satisfied
```

For safety, arbitrary LLM code is **not blindly applied**. It creates reviewable agent-specific patch plans. You can enable deterministic patch library later.

## Premium API docs and Postman

Generated:

```text
docs/API_REFERENCE.md
docs/api_reference_index.json
generated/openapi.json
generated/postman_collection.json
generated/negative_tests.postman_collection.json
generated/edge_tests.postman_collection.json
generated/data_references.json
generated/environment.postman_environment.json
generated/qaira_tests.json
```

Postman now includes:

```text
status code assertions
response time assertions
response body checks
extractors for id/token
negative missing-required tests
edge empty-value tests
collection variables
data reference payloads
```

## Build

```bash
docker build -t qaira/semantic-compiler:self-healing-docs .
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
  qaira/semantic-compiler:self-healing-docs
```
