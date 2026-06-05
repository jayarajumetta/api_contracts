# V49 ImportAwareServiceResolver + ExportResolver

V48 revealed the bottleneck:

```text
service call found
implementation not found
```

V49 resolves:

```js
import aiKnowledgeService from './ai-knowledge.service'
aiKnowledgeService.createKnowledge(payload)
```

to:

```text
route file
→ import local name
→ service file
→ exported object/class/default instance
→ method implementation
→ payload field usage
```

## Supported export styles

```js
export default { createKnowledge() {} }
module.exports = { createKnowledge }
module.exports = { createKnowledge: async function(payload) {} }
exports.createKnowledge = async function(payload) {}
class Service { async createKnowledge(payload) {} }
export default new Service()
const service = { createKnowledge(payload) {} }
module.exports = service
```

## Outputs

```text
validation/import_aware_service_resolution_report.json
validation/export_resolution_report.json
validation/service_implementation_registry.json
diagnostics/v49_service_resolution_diagnostics.json
```
