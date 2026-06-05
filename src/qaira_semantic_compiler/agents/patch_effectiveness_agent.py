from qaira_semantic_compiler.core.context import AgentResult

class PatchEffectivenessAgent:
    name = "PatchEffectivenessAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        history = self.ctx.read_json("runtime/iteration_context.json", {}) or {}
        iterations = history.get("iterations", [])
        if len(iterations) < 2:
            report = {"enoughIterations": False, "message": "Need at least two iterations to compare patch effectiveness."}
            self.ctx.write_json("self_healing/patch_effectiveness_report.json", report)
            return AgentResult(self.name, "success", 0.7, {"compared": False}, report)

        prev = iterations[-2]
        curr = iterations[-1]
        prev_score = float(prev.get("score", 0) or 0)
        curr_score = float(curr.get("score", 0) or 0)
        delta = round(curr_score - prev_score, 2)

        prev_summary = prev.get("summary", {})
        curr_summary = curr.get("summary", {})
        metric_delta = {}
        for k, v in curr_summary.items():
            if isinstance(v, (int, float)) and isinstance(prev_summary.get(k), (int, float)):
                metric_delta[k] = round(v - prev_summary.get(k), 2)

        report = {
            "enoughIterations": True,
            "previousIteration": prev.get("iteration"),
            "currentIteration": curr.get("iteration"),
            "previousScore": prev_score,
            "currentScore": curr_score,
            "scoreDelta": delta,
            "improved": delta >= 0,
            "metricDelta": metric_delta,
            "rollbackRecommended": delta < -float((self.ctx.config.get("patch_library", {}) or {}).get("rollback_drop_tolerance", 1.0))
        }
        self.ctx.write_json("self_healing/patch_effectiveness_report.json", report)
        return AgentResult(self.name, "success", 0.9, {"scoreDelta": delta, "improved": report["improved"]}, report)
