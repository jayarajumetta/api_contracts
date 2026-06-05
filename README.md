# QAira Semantic Compiler Platform V57 — Graph Completion Release

V57 is a focused fix release over V56.

The V56 output proved that discovery is good, but graph traversal is weak:

```text
Import-aware resolutions      0
DTO attachments               1 / 60
Shape propagations            0
Function return propagations  0
Actionable recovery           0 / 37
```

V57 focuses only on graph completion.

## V57 Adds

### 1. ImportHydrationAgentV57

Repairs unresolved service imports like:

```js
const authService = require("../services/auth.service")
```

by explicitly checking:

```text
../services/auth.service.js
../services/auth.service.ts
../services/auth.service/index.js
../services/auth.service/index.ts
```

and common service module patterns.

### 2. ServiceCallGraphAgentV57

Builds edges:

```text
Route → Handler → Service → Repository → ORM
```

based on import aliases, service calls, implementation files, and method names.

### 3. ShapePropagationAgentV57

Propagates:

```text
request.body → alias → service call → service method param → field usage
```

and enriches request schemas.

### 4. ReturnPropagationAgentV57

Propagates:

```text
service result → handler variable → reply.send / return
```

and improves response schema evidence.

### 5. DTOAttachmentAgentV57

Replaces weak string similarity with call-graph-aware attachment:

```text
route → service method signature → DTO/schema → request body
```

## New Outputs

```text
/output/graph_completion/import_hydration_v57_report.json
/output/graph_completion/service_call_graph_v57.json
/output/graph_completion/shape_propagation_v57_report.json
/output/graph_completion/return_propagation_v57_report.json
/output/graph_completion/dto_attachment_v57_report.json
/output/graph_completion/graph_completion_summary.json
```

## Docker Run

```bash
docker build -t qaira/semantic-compiler:v57 .

docker run --rm \
  -v /absolute/path/to/source:/repo:ro \
  -v /absolute/path/to/output:/output \
  -v /absolute/path/to/config.yaml:/config/config.yaml:ro \
  -v /absolute/path/to/learning:/learning \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  qaira/semantic-compiler:v57
```
