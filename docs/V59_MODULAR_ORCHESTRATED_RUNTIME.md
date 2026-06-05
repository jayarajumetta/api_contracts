# V59 Modular Orchestrated Runtime

## Architectural decision

Yes, separating each agent into its own `.py` file is the right long-term architecture.

## Mature structure

```text
main.py should not own orchestration forever.
orchestrator_v59.py controls execution.
agents/*.py each own one responsibility.
core/*.py owns shared runtime primitives.
```

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

## Fail-safe behavior

```text
agent throws exception
↓
SafeAgentRunner captures traceback
↓
writes /output/agents/<agent>/result.json
↓
continues if fail_open=true
```

## Next migration

Move inner legacy compiler agents from `main.py` into `agents/` one by one:

```text
InlineHandlerCompilerAgent
ImportGraphAgent
GraphCompletionAgent
DTOAttachmentAgent
TestGeneratorAgent
```
