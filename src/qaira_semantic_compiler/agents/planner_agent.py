from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult

class PlannerAgent:
    name = "PlannerAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        stages = (self.ctx.config.get("orchestrator") or {}).get("stages", [])
        plan = {
            "executionModel": "deterministic_first_llm_assisted",
            "stages": stages,
            "guards": {
                "failOpen": True,
                "qualityGate": True,
                "verifier": True,
                "cache": bool((self.ctx.config.get("cache") or {}).get("enabled", True)),
                "budget": bool((self.ctx.config.get("budget") or {}).get("enabled", True)),
            }
        }
        self.ctx.write_json("runtime/execution_plan.json", plan)
        return AgentResult(self.name, "success", 0.95, {"stageCount": len(stages)}, plan)
