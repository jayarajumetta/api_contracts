from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
import json

class OutputAnalyzerAgent:
    name = "OutputAnalyzerAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        summary_path = self.ctx.output / "summary" / "scan_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        strengths, weaknesses = [], []
        if summary.get("bodyDetectionRate", 0) >= 90:
            strengths.append("body_detection")
        if summary.get("v57ImportHydrated", 0) > 0:
            strengths.append("import_hydration")
        for key in ["schemaAttachmentsResolved", "v57DtoAttached", "shapePropagations", "v48ActionableRecovered"]:
            if summary.get(key, 0) == 0:
                weaknesses.append(key)
        analysis = {"summary": summary, "strengths": strengths, "weaknesses": weaknesses}
        self.ctx.write_json("analysis/output_analysis_v59.json", analysis)
        confidence = 0.9 if summary else 0.1
        return AgentResult(self.name, "success", confidence, {"strengths": len(strengths), "weaknesses": len(weaknesses)}, analysis)
