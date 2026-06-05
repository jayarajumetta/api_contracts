# V43 Function Return Propagation + Header Agent V2

## Function Return Propagation

Detects:

```js
const payload = buildPayload(body)
service.create(payload)

function buildPayload(body) {
  return {
    name: body.name,
    email: body.email
  }
}
```

Outputs:

```text
validation/function_return_propagation_report.json
validation/builder_shape_registry.json
```

## Header Agent V2

Detects:

```js
request.headers.authorization
request.headers['authorization']
request.header('authorization')
request.get('authorization')
ctx.headers.authorization
ctx.request.headers.authorization
reply.request.headers.authorization
```

## Cookie Agent V2

Detects:

```js
request.cookies.session
request.cookies['session']
ctx.cookies.session
ctx.request.cookies.session
```

## Success Criteria

```text
functionReturnPropagations > 0
headersDiscovered > 0
falsePositiveGETBodies = 0
```
