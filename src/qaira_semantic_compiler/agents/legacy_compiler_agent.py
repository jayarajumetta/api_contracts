from __future__ import annotations

from qaira_semantic_compiler.core.context import AgentResult
import json
import inspect


class LegacySemanticCompilerAgent:
    name = "LegacySemanticCompilerAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        from qaira_semantic_compiler.main import Orchestrator

        cfg_report = {"source": "v60_modular_orchestrator"}
        changed = self.ctx.changed_files or ""

        # Supports both old and newer Orchestrator signatures.
        try:
            sig = inspect.signature(Orchestrator)
            param_count = len(sig.parameters)
        except Exception:
            param_count = 6

        if param_count <= 1:
            rc = Orchestrator(self.ctx.config).run()
        else:
            rc = Orchestrator(
                self.ctx.source,
                self.ctx.output,
                self.ctx.learning,
                changed,
                self.ctx.config,
                cfg_report,
            ).run()

        summary_path = self.ctx.output / "summary" / "scan_summary.json"
        summary = {}
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        confidence = min(1.0, (summary.get("bodyDetectionRate", 0) or 0) / 100) if summary else 0.4
        return AgentResult(
            self.name,
            "success" if rc == 0 else "failed",
            confidence,
            summary,
            {"returnCode": rc, "summary": summary},
        )
