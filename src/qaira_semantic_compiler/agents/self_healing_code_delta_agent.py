from qaira_semantic_compiler.core.context import AgentResult
from pathlib import Path
import json

class SelfHealingCodeDeltaAgent:
    name = "SelfHealingCodeDeltaAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        cfg = self.ctx.config.get("self_healing", {}) or {}
        advice = self.ctx.state.get("selfHealingLLMAdvice") or self.ctx.read_json("self_healing/llm_advice.json", {}) or {}
        deltas = advice.get("suggestedAgentDeltas") or []

        allowed = set(cfg.get("allowed_patch_agents", []))
        apply_code = bool(cfg.get("apply_generated_agent_code", False))
        generated = []
        blocked = []
        applied = []

        for d in deltas:
            agent = d.get("agentName") or d.get("agent")
            confidence = float(d.get("confidence", 0.0) or 0.0)
            if agent not in allowed or confidence < 0.60:
                blocked.append({"delta": d, "reason": "agent_not_allowed_or_low_confidence"})
                continue

            patch = self.generate_safe_patch(agent, d)
            if patch:
                generated.append(patch)
                self.write_patch_artifact(agent, patch)
                if apply_code and patch.get("safeToApply"):
                    # This runtime intentionally does not apply arbitrary LLM code.
                    # Only future deterministic patch library items can be applied.
                    applied.append({"agent": agent, "status": "not_applied", "reason": "no_deterministic_patch_library_entry"})
            else:
                blocked.append({"delta": d, "reason": "no_safe_patch_template"})

        report = {
            "mode": "safe_agent_specific_delta_generation",
            "generatedPatchPlans": generated,
            "blockedDeltas": blocked,
            "applied": applied,
            "applyGeneratedAgentCode": apply_code,
            "note": "Arbitrary LLM code is not directly applied. Patch plans are generated and committed for review unless deterministic patch library is added."
        }
        self.ctx.write_json("self_healing/code_delta_report.json", report)
        return AgentResult(self.name, "success", 0.85, {"generated": len(generated), "blocked": len(blocked)}, report)

    def generate_safe_patch(self, agent, delta):
        templates = {
            "BodyDiscoveryAgent": "Expand body alias and service argument extraction patterns.",
            "ServiceBodyFieldAgent": "Improve route service-call argument to service method parameter mapping.",
            "DbWriteFieldAgent": "Add scoped DB write extractors for called service method only.",
            "TestGenerationAgent": "Add richer assertions, extractors, and data references.",
            "RouteDiscoveryAgent": "Add repository-specific route call patterns to balanced parser.",
            "ServiceGraphAgent": "Improve import and service call resolution."
        }
        if agent not in templates:
            return None
        return {
            "agent": agent,
            "file": f"src/qaira_semantic_compiler/agents/{self.agent_file(agent)}",
            "patchIntent": delta.get("patchIntent") or templates[agent],
            "repoSpecificInput": delta.get("repoSpecificInput"),
            "reason": delta.get("reason"),
            "confidence": delta.get("confidence"),
            "safeToApply": False,
            "reviewRequired": True
        }

    def agent_file(self, agent):
        mapping = {
            "RouteDiscoveryAgent": "route_discovery_agent.py",
            "BodyDiscoveryAgent": "body_discovery_agent.py",
            "ServiceGraphAgent": "service_graph_agent.py",
            "ServiceBodyFieldAgent": "service_body_field_agent.py",
            "DbWriteFieldAgent": "db_write_field_agent.py",
            "TestGenerationAgent": "test_generation_agent.py",
        }
        return mapping.get(agent, agent.lower() + ".py")

    def write_patch_artifact(self, agent, patch):
        path = self.ctx.output / "codegen" / "agent_deltas" / (agent + ".patch_plan.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(patch, indent=2, default=str), encoding="utf-8")
