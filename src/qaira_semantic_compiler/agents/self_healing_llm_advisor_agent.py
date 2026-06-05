from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.llm_client import LLMClient

class SelfHealingLLMAdvisorAgent:
    name = "SelfHealingLLMAdvisorAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        quality = self.ctx.read_json("quality/quality_gate_report.json", {}) or {}
        perf = self.ctx.state.get("agentPerformanceReport") or self.ctx.read_json("self_healing/agent_performance_report.json", {}) or {}
        cfg = self.ctx.config.get("self_healing", {}) or {}

        threshold = float((self.ctx.config.get("quality_gate") or {}).get("min_score_percent", 90))
        score = float(quality.get("score", 0) or 0)
        weak_agents = perf.get("weakAgents", [])

        should_call = bool(cfg.get("llm_advisor_enabled", True)) and (weak_agents or score < threshold)

        prompt_context = {
            "instruction": "Review agent performance. Suggest repo-specific input adjustments and safe code deltas for specific agent files only.",
            "quality": quality,
            "agentPerformance": perf,
            "rules": {
                "doNotModify": ["orchestrator.py", "core/runner.py", "core/context.py", "core/llm_client.py"],
                "outputFormat": {
                    "accepted": "boolean",
                    "suggestedAgentDeltas": [
                        {
                            "agentName": "SpecificAgentName",
                            "reason": "why",
                            "repoSpecificInput": "what evidence/input this agent should use next iteration",
                            "patchIntent": "what logic to change",
                            "confidence": 0.0
                        }
                    ]
                }
            }
        }

        if not should_call:
            result = {
                "skipped": True,
                "reason": "quality_passed_and_no_weak_agents",
                "score": score,
                "threshold": threshold,
                "suggestedAgentDeltas": []
            }
        else:
            result = LLMClient(self.ctx, self.logger).review(
                "SelfHealingLLMAdvisorAgent",
                prompt_context,
                default={"accepted": score >= threshold, "score": score, "suggestedAgentDeltas": []}
            )

        self.ctx.state["selfHealingLLMAdvice"] = result
        self.ctx.write_json("self_healing/llm_advice.json", result)
        return AgentResult(self.name, "success", 0.9, {"llmSkipped": result.get("skipped", False)}, result)
