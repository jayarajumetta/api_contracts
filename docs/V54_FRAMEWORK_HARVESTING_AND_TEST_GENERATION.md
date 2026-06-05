# V54 Framework Harvesting + Test Generation

## Missing pieces added

```text
Runtime/framework-native contract harvesting
AST comment/docstring extraction
Validation constraint mapping
Configurable test generation
Request relation/order engine
LLM ordering fallback prompt
```

## Test types

```yaml
test_generation:
  types:
    - postman
    - curl
    - qaira
    - rest_assured
    - playwright_api
    - k6
    - jmeter
```

## Outputs

```text
harvest/framework_contracts.json
harvest/doc_comment_registry.json
harvest/validation_constraints.json

testing/request_sequence_plan.json
testing/request_dependency_graph.json
testing/test_data_references.json

generated/curl_requests.sh
generated/qaira_tests.json
generated/rest_assured_tests.java
generated/playwright_api_tests.spec.ts
generated/k6_tests.js
generated/jmeter_plan.jmx
```
