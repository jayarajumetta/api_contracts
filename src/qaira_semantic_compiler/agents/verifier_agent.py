from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
import json

class VerifierAgent:
    name = "VerifierAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        checks = []
        def check_json(rel, required_keys=None):
            p = self.ctx.output / rel
            item = {"file": rel, "exists": p.exists(), "validJson": False, "nonEmpty": False}
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    item["validJson"] = True
                    item["nonEmpty"] = bool(data)
                    if required_keys:
                        item["requiredKeysPresent"] = all(k in data for k in required_keys)
                except Exception as e:
                    item["error"] = str(e)
            checks.append(item)
        check_json("summary/scan_summary.json")
        check_json("generated/openapi.json", ["paths"])
        check_json("generated/postman_collection.json")
        check_json("discovery/unified_api_contracts.json")
        check_json("final/final_test_generation_report.json")
        passed = sum(1 for c in checks if c.get("exists") and (c.get("validJson") or c["file"].endswith(".md")))
        result = {"checks": checks, "passed": passed, "total": len(checks)}
        self.ctx.write_json("quality/verifier_report.json", result)
        conf = passed / max(len(checks), 1)
        return AgentResult(self.name, "success" if conf >= 0.6 else "failed_open", conf, result, result)
