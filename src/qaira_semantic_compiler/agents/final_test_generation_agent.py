from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
import json, shutil

class FinalTestGenerationAgent:
    name = "FinalTestGenerationAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        generated = []
        gen_dir = self.ctx.output / "generated"
        final_dir = self.ctx.output / "final" / "generated"
        final_dir.mkdir(parents=True, exist_ok=True)
        if gen_dir.exists():
            for p in gen_dir.iterdir():
                if p.is_file():
                    shutil.copy2(p, final_dir / p.name)
                    generated.append(p.name)
        report = {"overridePrevious": True, "generated": generated}
        self.ctx.write_json("final/final_test_generation_report.json", report)
        return AgentResult(self.name, "success", 0.95 if generated else 0.4, report, report)
