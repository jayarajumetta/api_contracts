# QAira Semantic Compiler Platform V55 — Active LLM Iteration Runtime

V55 is the active closed-loop runtime version.

It preserves everything learned from V32–V54:

```text
Route discovery
Body detection
Object shape analyzer
Request context engine
Query/path/header/cookie separation
Module resolution audit
Import registry hydration
Framework-native harvesting
Validation constraint harvesting
Configurable test generation
Relationship sequencing
LLM governance artifacts
```

and adds the missing runtime behavior:

```text
RepoCloneAgent
StageLLMDecisionGate
SuggestedTaskExecutor
IterationMemoryStore
LLMResultsAnalyserLoop
FinalTestGenerationAgent
LLMCodeGenerationAgent
GitCommitPushAgent
```

## V55 Execution Order

```text
0. Read config
1. RepoCloneAgent
   - clone repo from config.repo.url if enabled
   - checkout develop/default branch
   - source_dir becomes cloned repo/source_subdir

2. Active Iteration Loop
   default max_iterations = 50

   For each iteration:
     a. Run deterministic agent stages
     b. After every stage:
        - capture worked/failed outcome
        - ask LLM true/false: was outcome correct?
        - if false/failure, ask LLM for deterministic recovery tasks
        - execute allowed suggested tasks only
        - store worked/failed/LLM-suggested worked patterns
     c. LLMResultsAnalyser reads full output volume
        - what worked
        - what failed
        - what suggested worked
        - score
        - satisfied true/false
        - next iteration suggestions
     d. Repeat until:
        - satisfied = true
        - score >= threshold
        - max_iterations reached

3. Final one-time stages outside loop:
   - FinalTestGenerationAgent overrides earlier generated tests
   - LLMCodeGenerationAgent creates patches from established worked patterns
   - GitCommitPushAgent commits and pushes to target branch if enabled
   - PR report generated if enabled
```

## Safe Defaults

All destructive/remote operations are disabled unless explicitly configured:

```yaml
repo.enabled: false
llm.enabled: false
llm_iteration.enabled: false
code_generation.enabled: false
git_push.enabled: false
pull_request.enabled: false
```

Credentials must use environment variables:

```bash
OPENAI_API_KEY
GIT_USERNAME
GIT_TOKEN
```

## Major Output Folders

```text
/output/iterations/iteration_*/...
/output/llm/stage_reviews/...
/output/llm/results_analyser/...
/output/llm/suggested_tasks/...
/output/learning/worked_patterns.json
/output/learning/failed_patterns.json
/output/learning/llm_suggested_worked_patterns.json
/output/final/final_test_generation_report.json
/output/git/code_push_report.json
/output/git/pr_report.json
/output/verbose/*.jsonl
```

## Docker Run

```bash
docker build -t qaira/semantic-compiler:v55 .

docker run --rm \
  -v /absolute/path/to/output:/output \
  -v /absolute/path/to/config.yaml:/config/config.yaml:ro \
  -v /absolute/path/to/learning:/learning \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e GIT_USERNAME="$GIT_USERNAME" \
  -e GIT_TOKEN="$GIT_TOKEN" \
  qaira/semantic-compiler:v55
```

For local source without clone:

```bash
docker run --rm \
  -v /absolute/path/to/source:/repo:ro \
  -v /absolute/path/to/output:/output \
  -v /absolute/path/to/config.yaml:/config/config.yaml:ro \
  -v /absolute/path/to/learning:/learning \
  qaira/semantic-compiler:v55
```

For git push/code generation, mount a writable workspace and enable the config explicitly.

## Config location

The updated V55 config is included in both locations:

```text
config.example.yaml
config/config.example.yaml
```

Use either as your mounted config:

```bash
-v /absolute/path/to/config.example.yaml:/config/config.yaml:ro
```
# api_contracts
