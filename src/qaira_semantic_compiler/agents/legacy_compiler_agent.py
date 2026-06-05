from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
from pathlib import Path
import json

class LegacySemanticCompilerAgent:
    name = "LegacySemanticCompilerAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        from qaira_semantic_compiler.main import Orchestrator
        cfg_report = {"source": "v59_modular_orchestrator"}
        changed = self.ctx.changed_files or ""
        rc = Orchestrator(self.ctx.source, self.ctx.output, self.ctx.learning, changed, self.ctx.config, cfg_report).run()
        summary_path = self.ctx.output / "summary" / "scan_summary.json"
        summary = {}
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        confidence = min(1.0, (summary.get("bodyDetectionRate", 0) or 0) / 100) if summary else 0.4
        return AgentResult(self.name, "success" if rc == 0 else "failed", confidence, summary, {"returnCode": rc, "summary": summary})
