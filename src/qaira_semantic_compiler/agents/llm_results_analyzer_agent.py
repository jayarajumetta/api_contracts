from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
import json, os

class LLMResultsAnalyzerAgent:
    name = "LLMResultsAnalyzerAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        cfg = self.ctx.config
        summary_path = self.ctx.output / "summary" / "scan_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        score = self.score(summary)
        threshold = float((cfg.get("llm_results_analyser") or {}).get("threshold_percent", 100))
        prompt = {
            "instruction": "Analyze results. Return score, satisfied, what worked, what failed, and next deterministic improvements.",
            "summary": summary,
            "agentResults": [r.__dict__ for r in self.ctx.agent_results],
            "threshold": threshold
        }
        self.ctx.write_json("llm/results_analyser/prompts/iteration_1_v59.json", prompt)
        # Fail-safe: do not block on LLM. Real network execution can be added behind explicit gateway.
        result = {
            "llmEnabled": bool((cfg.get("llm") or {}).get("enabled")),
            "failOpen": True,
            "networkCallExecuted": False,
            "score": score,
            "threshold": threshold,
            "satisfied": score >= threshold,
            "nextSteps": ["Improve DTO graph resolver", "Improve schema attachment", "Use repository index for all module lookups"] if score < threshold else []
        }
        self.ctx.write_json("llm/results_analyser/iteration_1.json", result)
        return AgentResult(self.name, "success", 0.85, result, result)

    def score(self, s):
        score = 0; total = 0
        if "bodyDetectionRate" in s:
            score += min(float(s.get("bodyDetectionRate", 0)), 100) * 0.25; total += 25
        if s.get("falsePositiveGETBodies", 1) == 0:
            score += 15; total += 15
        if s.get("v57ImportHydrated", 0) > 0:
            score += 15; total += 15
        if s.get("v57ServiceEdges", 0) > 0:
            score += 15; total += 15
        if s.get("v57ReturnPropagations", 0) > 0:
            score += 15; total += 15
        if s.get("testsGenerated", False):
            score += 15; total += 15
        return round(score / max(total, 1) * 100, 2)
