# V42 Request Context Engine

V42 fixes request-location misclassification.

## Contexts

```text
BODY
QUERY
PATH
HEADER
COOKIE
```

## Examples

```js
request.query.page        -> query parameter
request.params.id         -> path parameter
request.headers["x-id"]   -> header
request.cookies.session   -> cookie
request.body.name         -> body
```

## Important Rule

```text
GET / HEAD / OPTIONS never get request bodies.
```

## Outputs

```text
validation/request_context_report.json
validation/query_param_registry.json
validation/path_param_registry.json
validation/header_registry.json
validation/cookie_registry.json
diagnostics/request_context_diagnostics.json
```
