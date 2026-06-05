from __future__ import annotations
from pathlib import Path
import json, datetime

class IterationContextStore:
    def __init__(self, ctx):
        self.ctx = ctx
        self.path = ctx.output / "runtime" / "iteration_context.json"
        self.data = {
            "createdAt": datetime.datetime.utcnow().isoformat()+"Z",
            "purpose": "single compact context for LLM review and deterministic remediation",
            "iterations": [],
            "llmCalls": [],
            "best": None,
        }

    def load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self

    def add_iteration(self, iteration, agent_results, summary, quality, analysis=None):
        item = {
            "iteration": iteration,
            "score": quality.get("score", 0),
            "passed": quality.get("passed", False),
            "summary": compact_summary(summary),
            "agents": [
                {
                    "name": r.name,
                    "status": r.status,
                    "confidence": r.confidence,
                    "metrics": r.metrics,
                    "errors": [{"message": e.get("message","")[:500]} for e in (r.errors or [])]
                }
                for r in agent_results
            ],
            "analysis": compact_analysis(analysis or {})
        }
        self.data["iterations"].append(item)
        if not self.data.get("best") or item["score"] > self.data["best"].get("score", -1):
            self.data["best"] = {"iteration": iteration, "score": item["score"], "summary": item["summary"]}
        self.write()

    def add_llm_call(self, name, request_summary, response):
        self.data.setdefault("llmCalls", []).append({
            "name": name,
            "requestSummary": request_summary,
            "response": response
        })
        self.write()

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, default=str), encoding="utf-8")

def compact_summary(s):
    keys = [
        "apiContracts","bodyExpected","bodyDetected","bodyFieldsKnown","bodyDetectionRate","bodyFieldKnownRate",
        "pathParamsDiscovered","queryParamsDiscovered","headersDiscovered","serviceEdges","schemasDiscovered",
        "inferredSchemas","declaredSchemaAttachments","inferredSchemaAttachments","serviceBodyPatterns",
        "dbWritePatterns","testsGenerated","negativeTestsGenerated","edgeTestsGenerated"
    ]
    return {k:s.get(k) for k in keys if k in s}

def compact_analysis(a):
    return {
        "accepted": a.get("accepted"),
        "score": a.get("score"),
        "threshold": a.get("threshold"),
        "issues": a.get("issues", [])[:10],
        "nextRemediations": a.get("nextRemediations", [])[:10]
    }
