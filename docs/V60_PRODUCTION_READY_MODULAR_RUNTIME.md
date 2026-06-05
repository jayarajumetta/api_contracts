# V60 Production-Ready Modular Runtime

## Agent contract

Every agent returns:

```json
{
  "name": "AgentName",
  "status": "success|failed|failed_open",
  "confidence": 0.0,
  "metrics": {},
  "outputs": {},
  "errors": [],
  "started_at": "...",
  "ended_at": "..."
}
```

## Fail-safe path

```text
agent error
↓
SafeAgentRunner captures traceback
↓
writes /output/agents/<AgentName>/result.json
↓
continues if fail_open=true
```

## Best practice decision

Separating agents into different `.py` files is the right approach.

Benefits:

```text
clean ownership
agent-specific logs
agent-specific metrics
agent-specific tests
agent-specific retry/recovery
easy replacement of individual agents
parallelization-ready
```

V60 is the first production-safe runtime structure.
