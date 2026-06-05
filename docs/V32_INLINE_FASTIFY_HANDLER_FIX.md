# V32 Inline Fastify Handler Fix

## Problem in V31

The route parser selected identifiers inside inline handlers as route handler names:

```text
POST /auth/login -> body
POST /app-types  -> body
POST /projects   -> item
```

This caused:

```text
body_detected = 0
requestResolved = 0
```

## Fix in V32

V32 identifies inline handlers structurally:

```ts
fastify.post('/x', async (request, reply) => {
  const body = request.body
})
```

It creates:

```text
Route -HANDLED_BY-> InlineHandler
InlineHandler -EXPECTS_BODY-> request.body
```

## Detection supported

```ts
const body = request.body
const { email, password } = request.body
request.body.email
body.email
const { body } = request
body.email
```

## Diagnostics

```text
diagnostics/body_detection_report.json
diagnostics/body_detection_detail.json
diagnostics/handler_detection_report.json
```
