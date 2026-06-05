# V51 Resolver Wiring Audit + Execution Trace

V50 showed:

```json
{
  "total": 0,
  "resolved": 0,
  "unresolved": 0
}
```

That means the module resolver was not invoked.

## V51 objective

Every discovered import/require/export must produce an execution trace record.

## Outputs

```text
diagnostics/resolver_wiring_audit.json
diagnostics/resolver_execution_trace.json
diagnostics/import_pipeline_comparison.json
diagnostics/module_resolution_diagnostics.json
validation/module_resolution_report.json
validation/module_resolution_registry.json
```

## Success criteria

```json
{
  "imports_discovered": "> 0",
  "imports_attempted": "same as discovered or close",
  "imports_resolved": "> 0"
}
```

## What to inspect first

```text
diagnostics/import_pipeline_comparison.json
```

If:

```text
imports_discovered > 0
imports_attempted = 0
```

the resolver is still not wired.

If:

```text
imports_attempted > 0
imports_resolved = 0
```

the resolver logic needs fixing.

If:

```text
imports_resolved > 0
v48ActionableRecovered still 0
```

then service export matching is the next bottleneck.
