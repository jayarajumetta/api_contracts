from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult

class CodeGenerationAgent:
    name = "CodeGenerationAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        cfg = self.ctx.config.get("code_generation") or {}
        if not cfg.get("enabled", False):
            result = {"enabled": False, "reason": "code_generation_disabled", "patches": []}
        elif cfg.get("generate_patch_only", True):
            result = {"enabled": True, "mode": "patch_plan_only", "patches": [], "reason": "LLM patch generation is fail-safe/deferred"}
        else:
            result = {"enabled": True, "patches": [], "reason": "apply_patch_false_or_no_patches"}
        self.ctx.write_json("llm/code_patch_plan.json", result)
        return AgentResult(self.name, "success", 0.8, result, result)
