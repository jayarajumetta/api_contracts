# V63 Accuracy Restore

## Problem

Old regex:

```text
route(path, async (req, reply) => ...)
```

was captured only as:

```text
async (req
```

because the regex stopped at the first `)`.

## Fix

Balanced route-call scanner:

```text
find route call
scan to matching parenthesis
split top-level arguments
extract full inline handler
```

## Expected impact

```text
bodyDetected should recover from 1 toward the earlier 119 level.
service graph / shape propagation should also improve because raw handler text is complete again.
```
