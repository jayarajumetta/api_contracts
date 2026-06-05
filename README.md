# QAira Semantic Compiler Platform V56

V56 is a focused correction over V55.

V55 added governance artifacts, but the uploaded output showed the active runtime did not truly improve:

```text
v49ImportAwareResolutions = 0
schemaAttachmentsResolved = 0
shapePropagations = 0
functionReturnPropagations = 0
v48ActionableRecovered = 0
```

V56 moves from "LLM everywhere" to a better production architecture:

```text
Agent runs
↓
Confidence Engine scores outcome
↓
Only low-confidence/failure agents call LLM
↓
Suggested deterministic tasks are recorded/executed if allowed
↓
Iteration loop repeats up to configured max
↓
Final tests generated once
↓
Optional repo clone / commit / push / PR final stage
```

## V56 Adds

### 1. RuntimeExecutionManager

Real iteration controller with configurable max iterations.

Default:

```yaml
runtime_execution:
  enabled: true
  max_iterations: 50
```

### 2. AgentConfidenceEngine

Every major stage gets a confidence score.

Only if:

```text
confidence < llm_invocation.confidence_threshold
```

or the stage fails, the LLM is asked.

Default:

```yaml
llm_invocation:
  mode: selective
  confidence_threshold: 0.80
```

### 3. SelectiveLLMInvocationAgent

Avoids the expensive and noisy pattern:

```text
every agent → LLM
```

Uses:

```text
low confidence / failure → LLM
```

### 4. VariablePropagationAgent

Targets:

```js
const payload = req.body
service.create(payload)
```

and extracts fields from:

```js
payload.name
payload.email
const { name, email } = payload
```

### 5. ResponsePropagationAgent

Targets:

```js
const result = await service.create(payload)
reply.send(result)
return result
```

and produces response propagation diagnostics.

### 6. DTOAttachmentAgent

Attempts to connect already discovered schemas to routes/handlers using:

```text
schema name similarity
route file names
handler names
validation wrapper names
request body aliases
service method names
```

This is intentionally deterministic before LLM.

### 7. RealRepoAgent

Configurable real clone / checkout / commit / push flow.

Safe by default:

```yaml
repo.enabled: false
git_push.push: false
```

When enabled, it can execute git commands inside the mounted container.

### 8. FinalTestGenerationAgent

Runs once after the iteration loop and overrides earlier test artifacts.

## Main Outputs

```text
/output/runtime/iteration_*/iteration_summary.json
/output/runtime/runtime_execution_report.json
/output/runtime/confidence_report.json
/output/runtime/selective_llm_invocation_report.json

/output/propagation/variable_propagation_report.json
/output/propagation/response_propagation_report.json
/output/propagation/dto_attachment_report.json

/output/final/final_test_generation_report.json
/output/git/repo_clone_report.json
/output/git/code_push_report.json
/output/git/pr_report.json
```

## Docker Run

Local source:

```bash
docker build -t qaira/semantic-compiler:v56 .

docker run --rm \
  -v /absolute/path/to/source:/repo:ro \
  -v /absolute/path/to/output:/output \
  -v /absolute/path/to/config.yaml:/config/config.yaml:ro \
  -v /absolute/path/to/learning:/learning \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  qaira/semantic-compiler:v56
```

Repo clone mode:

```bash
docker run --rm \
  -v /absolute/path/to/output:/output \
  -v /absolute/path/to/config.yaml:/config/config.yaml:ro \
  -v /absolute/path/to/learning:/learning \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e GIT_USERNAME="$GIT_USERNAME" \
  -e GIT_TOKEN="$GIT_TOKEN" \
  qaira/semantic-compiler:v56
```
