# V56 Confidence-Gated Runtime

V56 implements the agreed direction:

```text
agent runs
confidence engine scores
LLM only on low confidence/failure
iteration report written
final tests generated once
git push gated by config
```

## New agents

```text
RuntimeExecutionManagerV56
AgentConfidenceEngineV56
SelectiveLLMInvocationAgentV56
RealRepoAgentV56
VariablePropagationAgentV56
ResponsePropagationAgentV56
DTOAttachmentAgentV56
FinalTestGenerationAgentV56
GitCommitPushAgentV56
```

## Config highlights

```yaml
runtime_execution:
  max_iterations: 50

llm_invocation:
  mode: selective
  confidence_threshold: 0.80

repo:
  url: ""
  execute_git: false

git_push:
  push: false
  execute_git: false
```
