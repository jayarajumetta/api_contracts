# QAira Semantic Compiler — Public Repo Trial Runtime

Try QAira against a public GitHub repository without mounting source code or config.

## Required env vars

```text
QAIRA_REPO_URL   Public Git repo URL to analyze
OPENAI_API_KEY   OpenAI API key for one compact LLM advisory call
GIT_TOKEN        GitHub token for push / PR
```

Optional:

```text
QAIRA_REPO_BRANCH  branch/tag to clone
GIT_USERNAME       defaults to x-access-token if omitted
```

## Flow

```text
SourceRepoCloneAgent clones QAIRA_REPO_URL into /workspace/source-repo
The checkout becomes source dir
Compiler generates contracts, docs, Postman tests, curl, data refs
Self-healing/patch-library evaluates and plans safe improvements
Generated artifacts are committed to develop
PR is created to main when push succeeds
```

## Run with output in present directory

```bash
mkdir -p qaira-output qaira-learning

docker run --rm \
  -e PYTHONUNBUFFERED=1 \
  -e QAIRA_REPO_URL="https://github.com/<owner>/<repo>.git" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e GIT_TOKEN="$GIT_TOKEN" \
  -v "$PWD/qaira-output:/output" \
  -v "$PWD/qaira-learning:/learning" \
  qaira/semantic-compiler:public-repo-trial
```

## Verify outputs

```text
qaira-output/repo/source_repo_clone_report.json
qaira-output/summary/scan_summary.json
qaira-output/quality/quality_gate_report.json
qaira-output/generated/openapi.json
qaira-output/generated/postman_collection.json
qaira-output/docs/API_REFERENCE.md
qaira-output/git/finalization_report.json
```

If the public repo does not allow your token to push, the run still completes and writes Git diagnostics.
