# V53 LLM-Governed Iteration Engine

V53 adds controlled stage-level and iteration-level governance.

## Safe defaults

```yaml
llm.enabled: false
llm_iteration.enabled: false
code_generation.enabled: false
git_push.enabled: false
pull_request.enabled: false
```

## Outputs

```text
llm/stage_reviews/
llm/results_analyser/
llm/iterations/
learning/worked_patterns.json
learning/failed_patterns.json
git/code_push_report.json
git/pr_report.json
verbose/*.jsonl
```
