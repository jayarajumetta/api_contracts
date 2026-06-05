# V36 Import Graph DTO Trace

V36 fixes the exact V35 gap:

```text
3300 signatures found
0 useful signature DTO traces
```

## Why V35 did not improve

It matched service calls by method name only:

```text
create()
login()
update()
```

That is unsafe because many services have the same method names.

## V36 fix

V36 resolves service calls through import evidence:

```ts
import authService from '../services/auth.service'

authService.login(body)
```

becomes:

```text
controller file
→ imports ../services/auth.service
→ authService.login
→ auth.service.ts login(data: LoginRequest)
→ LoginRequest schema
```

## New outputs

```text
graph/import_graph.json
validation/import_registry.json
validation/service_call_resolution_report.json
validation/dto_trace_report.json
```

## Deterministic only

No LLM required.
