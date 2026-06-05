# V41 Shape Propagation Engine

V41 upgrades V40's object shape analyzer.

## Fixes

1. No request bodies for GET/HEAD/OPTIONS.
2. Spread expansion for local shape variables.
3. Object.assign merge tracking.
4. Builder return shape tracking.
5. Shape confidence scoring.
6. Shape learning store.

## Examples

```js
const payload = {
  name,
  email
}

service.create({
  ...payload,
  role
})
```

Output fields:

```text
name
email
role
```

## Outputs

```text
graph/shape_graph.json
validation/shape_registry.json
validation/shape_propagation_report.json
validation/shape_merge_report.json
validation/shape_confidence_report.json
diagnostics/shape_resolution_diagnostics.json
learning/object-shapes/patterns.json
```

## Success Criteria

```text
falsePositiveGETBodies = 0
shapePropagations > 0
shapeMerges > 0
bodyFieldsKnown increases over V40
```
