# V45 Schema Attachment Resolver

V45 solves:

```text
schemas discovered, but not attached to routes
```

## Supported patterns

```js
fastify.post('/login', { schema: loginSchema }, handler)
```

```js
fastify.post('/login', { schema: { body: loginBodySchema } }, handler)
```

```js
const opts = { schema: loginSchema }
fastify.post('/login', opts, handler)
```

```js
fastify.route({
  method: 'POST',
  url: '/login',
  schema: loginSchema
})
```

```js
module.exports = { schema: loginSchema }
export const routeOptions = { schema: loginSchema }
```

## Outputs

```text
validation/schema_attachment_report.json
validation/route_schema_link_report.json
validation/schema_attachment_registry.json
diagnostics/schema_attachment_diagnostics.json
```

## Success Criteria

```text
schemaAttachmentsFound > 0
schemaAttachmentsResolved > 0
unresolved routes decrease
```
