# V44 Unresolved Route Investigator

V44 focuses only on unresolved mutable routes.

## Engines

### ValidationChainResolver

```js
const body = loginSchema.parse(request.body)
const body = await loginSchema.validateAsync(request.body)
const { value } = schema.validate(request.body)
validate(loginSchema, request.body)
```

### ServiceInputUsageResolver

```js
const payload = request.body
authService.login(payload)
```

Then service:

```js
function login(payload) {
  payload.email
  payload.password
}
```

## Outputs

```text
validation/unresolved_routes.json
validation/unresolved_route_investigation_report.json
validation/validation_chain_report.json
validation/service_input_usage_report.json
validation/recovered_unresolved_contracts.json
diagnostics/unresolved_route_diagnostics.json
```

## Success Criteria

```text
unresolvedRecovered > 0
unresolvedAfterInvestigation decreases
```
