from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
import json

class QualityGateAgent:
    name = "QualityGateAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        summary_path = self.ctx.output / "summary" / "scan_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        score = self.score(summary)
        threshold = float((self.ctx.config.get("quality_gate") or {}).get("min_score_percent", 90))
        gate = {
            "score": score,
            "threshold": threshold,
            "passed": score >= threshold,
            "summary": summary,
            "recommendations": self.recommendations(summary)
        }
        self.ctx.write_json("quality/quality_gate_report.json", gate)
        return AgentResult(self.name, "success" if gate["passed"] else "failed_open", score / 100, gate, gate)

    def score(self, s):
        weights = (self.ctx.config.get("quality_gate") or {}).get("metric_weights", {})
        if not weights:
            weights = {
                "body_detection_rate": 20,
                "body_field_known_rate": 15,
                "import_hydration": 15,
                "service_edges": 15,
                "return_propagation": 10,
                "actionable_recovery": 10,
                "test_generation": 10,
                "artifact_validity": 5,
            }
        total = sum(weights.values()) or 1
        score = 0
        score += min(float(s.get("bodyDetectionRate", 0)), 100) * weights.get("body_detection_rate", 0) / 100
        score += min(float(s.get("bodyFieldKnownRate", 0)), 100) * weights.get("body_field_known_rate", 0) / 100
        score += (100 if s.get("v57ImportHydrated", 0) > 0 else 0) * weights.get("import_hydration", 0) / 100
        score += (100 if s.get("v57ServiceEdges", 0) > 0 else 0) * weights.get("service_edges", 0) / 100
        score += (100 if s.get("v57ReturnPropagations", 0) > 0 else 0) * weights.get("return_propagation", 0) / 100
        actionable = float(s.get("actionableUnresolvedRoutes", 0) or 0)
        score += (100 if actionable == 0 else max(0, 100 - actionable * 4)) * weights.get("actionable_recovery", 0) / 100
        score += (100 if s.get("testsGenerated", False) else 0) * weights.get("test_generation", 0) / 100
        score += weights.get("artifact_validity", 0)
        return round(score / total * 100, 2)

    def recommendations(self, s):
        out = []
        if s.get("v57DtoAttached", 0) == 0:
            out.append("Improve DTO graph resolver and direct validation schema attachment.")
        if s.get("v48ActionableRecovered", 0) == 0:
            out.append("Improve actionable recovery by using service graph and validation wrappers.")
        if s.get("shapePropagations", 0) == 0:
            out.append("Promote V57 shape propagation into legacy summary metrics.")
        return out
