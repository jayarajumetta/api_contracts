# QAira Semantic Compiler — Self-Healing Patch Library Runtime

This version implements the mature self-healing layer.

## What is new

```text
PatchLibrary
PatchLibraryAgent
PatchEffectivenessAgent
AgentPerformanceEvaluatorAgent integration
SelfHealingLLMAdvisorAgent integration
SelfHealingCodeDeltaAgent integration
```

## How it self-heals

```text
1. Agents run
2. Quality + agent performance are scored
3. Weak agents are identified
4. LLM can suggest repo-specific deltas, but only once and only with compact context
5. PatchLibrary maps weak agents / LLM deltas to approved deterministic patch actions
6. Patch actions mutate runtime config/pattern registry, not arbitrary code
7. Next iteration reruns agents with patched behavior
8. Patch effectiveness is measured
9. If quality is satisfied, artifacts/docs/tests are generated and pushed
```

## Why this is mature

It does not blindly execute LLM-generated Python code.

Instead:

```text
LLM suggestion -> approved action id -> deterministic runtime patch -> rerun -> measure score
```

## Patch outputs

```text
self_healing/patch_library_registry.json
self_healing/patch_library_report.json
self_healing/patch_effectiveness_report.json
self_healing/pre_patch_config_snapshot.json
self_healing/post_patch_effective_config.json
codegen/agent_deltas/*.patch_plan.json
```

## Build

```bash
docker build -t qaira/semantic-compiler:patch-library .
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
  qaira/semantic-compiler:patch-library
```

## Important

For safety:

```yaml
patch_library:
  allow_source_file_modification: false
```

This can later be upgraded to deterministic source transformations only after patch actions are proven.
