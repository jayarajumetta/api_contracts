# V40 Object Shape Analyzer

V40 solves the JavaScript object-literal payload pattern.

## Patterns

```js
service.create({
  name,
  email,
  role
})
```

```js
const payload = {
  title: request.body.title,
  priority: request.body.priority
}

service.create(payload)
```

```js
const payload = {
  ...request.body,
  created_by: user.id
}
```

```js
Object.assign({}, request.body, {
  status: 'ACTIVE'
})
```

## Output

```text
validation/object_shape_report.json
validation/object_shape_registry.json
diagnostics/schema_resolution_diagnostics.json
```

## Expected improvement

The key strategy should increase:

```text
object_shape_analyzer
```

and:

```text
bodyFieldsKnown
```

should increase from the V39 baseline.
