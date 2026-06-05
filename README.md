# QAira Semantic Compiler Platform V59 — Modular Orchestrated Runtime

V59 restructures the runtime into separated agent files and keeps the existing compiler as the core semantic compiler stage.

## Why V59

Your current config is powerful but the implementation was becoming hard to control because many agents lived inside one large `main.py`.

V59 introduces a production-style layout:

```text
src/qaira_semantic_compiler/
  orchestrator_v59.py
  main.py                         # legacy semantic compiler core
  core/
    context.py
    logging.py
    safe_runner.py
    repository_index.py
  agents/
    repo_clone_agent.py
    repository_index_agent.py
    legacy_compiler_agent.py
    output_analyzer_agent.py
    llm_results_analyzer_agent.py
    final_test_generation_agent.py
    code_generation_agent.py
    git_commit_push_agent.py
```

## Execution flow

```text
ModularOrchestratorV59
  ├── RepoCloneAgent
  ├── RepositoryIndexAgent
  ├── LegacySemanticCompilerAgent
  │     └── runs the full V58/V57 semantic compiler
  ├── OutputAnalyzerAgent
  ├── LLMResultsAnalyzerAgent
  ├── FinalTestGenerationAgent
  ├── CodeGenerationAgent
  └── GitCommitPushAgent
```

## Benefits

```text
agent-level logs
agent-level metrics
agent-level failure capture
fail-open recovery
central orchestrator control
clean place to move legacy agents one-by-one into modules
repository index built once
safe LLM behavior
safe git behavior
```

## Important outputs

```text
/output/agents/<AgentName>/result.json
/output/runtime/modular_orchestrator_report.json
/output/repository/repository_index_v59.json
/output/analysis/output_analysis_v59.json
/output/llm/results_analyser/iteration_1.json
/output/final/final_test_generation_report.json
/output/git/code_push_report.json
/output/verbose/console_progress.log
```

## Docker run

```bash
docker build -t qaira/semantic-compiler:v59 .

docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e GIT_USERNAME="$GIT_USERNAME" \
  -e GIT_TOKEN="$GIT_TOKEN" \
  -v /Users/jayarajumetta/MJ/qaira:/repo:ro \
  -v /Users/jayarajumetta/Downloads/volume/output:/output \
  -v /Users/jayarajumetta/Downloads/volume/config.yaml:/config/config.yaml:ro \
  -v /Users/jayarajumetta/Downloads/volume/learning:/learning \
  qaira/semantic-compiler:v59
```

## Config

The latest complete config is included in both:

```text
config.example.yaml
config/config.example.yaml
```
