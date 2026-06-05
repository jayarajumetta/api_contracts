# V34: V32 Stable Parser + V33 Validation Engine

## Why V34 exists

V32 worked well:

```text
bodyDetected: 114 / 123
fallbacks: 9
```

V33 added validation schemas but regressed parser behavior:

```text
bodyDetected: 0 / 123
fallbacks: 123
```

V34 fixes this by using V32 as the base and applying validation schemas only as enrichment.

## Enrichment order

1. Keep V32 inline body detection
2. If Fastify body fields exist, keep them
3. If fields are unknown, try named schema/DTO match
4. If fields exist, improve their type using inference
5. Never replace a detected body with empty schema

## Supported validation sources

- Zod
- Joi
- TypeBox
- Yup
- Fastify schema.body
- TypeScript interfaces/classes
- class-validator scaffold

## Read after run

```text
validation/validation_schema_registry.json
validation/schema_resolution_report.json
diagnostics/schema_resolution_diagnostics.json
diagnostics/body_detection_report.json
summary/scan_summary.json
```
