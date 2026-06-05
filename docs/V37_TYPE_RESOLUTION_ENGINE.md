# V37 Type Resolution Engine

V37 fixes the remaining gap after V36.

## V36 proof

```text
Import graph works.
Service call resolution works.
Function signatures are discovered.
```

## V36 gap

```text
service method → parameter type → DTO schema
```

was not fully resolved.

## V37 solution

```text
login(data: LoginRequest)
        ↓
LoginRequest
        ↓
interface/type/class/schema registry
        ↓
OpenAPI request body
```

## Supported wrappers

```text
Promise<T>
Partial<T>
Required<T>
Readonly<T>
Array<T>
T[]
Pick<T, 'a' | 'b'>
Omit<T, 'a'>
```

## Merge rule

V37 merges:

```text
DTO fields
+
observed body fields
```

It does not discard V32 inline body detections.

## New outputs

```text
validation/type_registry.json
validation/type_resolution_report.json
validation/dto_trace_report.json
validation/service_call_resolution_report.json
```
