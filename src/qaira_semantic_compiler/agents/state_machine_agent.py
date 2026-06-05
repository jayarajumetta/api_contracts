from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult

class StateMachineAgent:
    name = "StateMachineAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self, state="INIT", event="start"):
        item = {"state": state, "event": event}
        self.ctx.write_json(f"runtime/state/{state.lower()}_{event}.json", item)
        return AgentResult(self.name, "success", 0.95, item, item)
