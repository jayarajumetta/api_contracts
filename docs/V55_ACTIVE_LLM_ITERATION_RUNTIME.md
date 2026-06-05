# V55 Active LLM Iteration Runtime

## Preserved from V32–V54

```text
route discovery
body detection
object shape analyzer
request context classification
framework harvesting
validation constraint harvesting
test generation
relationship graph
LLM governance artifacts
module resolver audit
import registry hydration
```

## Added in V55

```text
RepoCloneAgent
StageLLMDecisionGate
SuggestedTaskExecutor
IterationMemoryStore
ActiveIterationRuntime
FinalTestGenerationAgent
LLMCodeGenerationAgent
GitCommitPushAgent
```

## Required repo config

```yaml
repo:
  enabled: true
  url: "https://github.com/org/repo.git"
  clone_dir: /workspace/repo
  source_subdir: ""
  default_branch: develop
  username_env: GIT_USERNAME
  token_env: GIT_TOKEN
```

## Iteration config

```yaml
llm_iteration:
  enabled: true
  max_iterations: 50
  threshold_percent: 100
  stop_when_satisfied: true
```

## Final one-time stages

```text
FinalTestGenerationAgent
LLMCodeGenerationAgent
GitCommitPushAgent
```

These run outside the loop after the patterns are established.
