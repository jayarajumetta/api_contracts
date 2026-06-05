# V48 Validation Wrapper Resolver + Service Semantic Tracer

V46 showed:

```text
validation_wrapper_candidate = 28
service_trace_required = 9
real_unresolved = 0
```

V48 targets only those 37 actionable routes.

## Validation Wrapper Resolver

```js
validate(loginSchema, request.body)
validateBody(loginSchema, request.body)
validateRequest(request.body, loginSchema)
loginSchema.parse(request.body)
loginSchema.safeParse(request.body)
loginSchema.validate(request.body)
loginSchema.validateAsync(request.body)
```

## Service Semantic Tracer

```js
authService.login(payload)
```

Then traces:

```js
function login(payload) {
  payload.email
  payload.password
}
```

and:

```js
const { email, password } = payload
```

## Outputs

```text
validation/validation_wrapper_resolution_report.json
validation/service_semantic_trace_report.json
validation/actionable_recovery_report.json
validation/recovered_actionable_contracts.json
diagnostics/v48_recovery_diagnostics.json
```

## Success Criteria

```text
v48ActionableRecovered > 0
validation_wrapper_candidate decreases
service_trace_required decreases
```
