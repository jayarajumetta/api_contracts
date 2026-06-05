# V46 Diagnostic Classifier

V46 does not try to recover more contracts. It tells us what the remaining unresolved routes actually are.

## Buckets

```text
body_not_expected
already_has_body
schema_in_handler_candidate
validation_wrapper_candidate
service_trace_required
object_shape_candidate
query_only_route
path_only_route
dynamic_runtime_only
real_unresolved
```

## Outputs

```text
diagnostics/route_classification_report.json
diagnostics/unresolved_classification_report.json
diagnostics/real_unresolved_payload_routes.json
diagnostics/next_action_report.json
validation/route_classification_registry.json
validation/real_unresolved_routes.json
```

## Why this matters

Instead of chasing:

```text
unresolved = 60
```

V46 tells us:

```text
body_not_expected = ?
real_unresolved = ?
service_trace_required = ?
validation_wrapper_candidate = ?
```

This makes V47 data-driven.
