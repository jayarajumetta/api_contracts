# V39 CommonJS Module Resolution

V38 showed the unresolved pattern:

```text
object_method_unresolved
```

especially for JavaScript services.

## V39 supports

```js
const service = require('./service')
const { create, update: updateUser } = require('./service')

module.exports = { create, update }
module.exports = serviceObject
exports.create = create
module.exports.create = create

export default { create, update }
export const service = { create, update }
```

## New graph

```text
IMPORT_GRAPH
EXPORT_GRAPH
MODULE_GRAPH
```

## Main outputs

```text
graph/module_graph.json
validation/module_registry.json
validation/service_call_resolution_report.json
```

## Expected improvement

The key metric should improve:

```text
object_method_unresolved ↓
commonjs_or_object_export_method ↑
bodyFieldsKnown ↑
```
