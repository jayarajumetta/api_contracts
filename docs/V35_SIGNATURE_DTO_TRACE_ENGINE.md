# V35 Signature-Based DTO Trace Engine

V35 enforces the deterministic design without relying on LLM.

## Main path

```text
Route
→ Inline handler
→ body alias
→ service call
→ function signature
→ parameter type
→ DTO/schema registry
→ request schema
```

## Example

```ts
const body = request.body
await authService.login(body)

export async function login(data: LoginRequest) {}
interface LoginRequest {
  email: string
  password: string
}
```

V35 resolves:

```text
body → login(data) → LoginRequest → { email, password }
```

## Outputs

```text
validation/function_signature_registry.json
validation/dto_trace_report.json
validation/schema_resolution_report.json
diagnostics/schema_resolution_diagnostics.json
```

## Important

V35 never replaces working V32 body detection with an empty result. Signature DTO trace is enrichment only.
