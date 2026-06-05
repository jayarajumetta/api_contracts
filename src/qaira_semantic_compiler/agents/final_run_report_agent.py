from qaira_semantic_compiler.core.context import AgentResult

class FinalRunReportAgent:
    name="FinalRunReportAgent"
    def __init__(self,ctx,logger):
        self.ctx=ctx
        self.logger=logger
    def run(self):
        report={
            "status":"completed",
            "bestIteration":self.ctx.state.get("bestIteration"),
            "finalSummary":self.ctx.read_json("summary/scan_summary.json",{}),
            "quality":self.ctx.read_json("quality/quality_gate_report.json",{}),
            "analysis":self.ctx.read_json("analysis/results_analysis.json",{}),
            "git":self.ctx.read_json("git/finalization_report.json",{}),
            "agents":[r.__dict__ for r in self.ctx.results]
        }
        self.ctx.write_json("runtime/final_run_report.json",report)
        return AgentResult(self.name,"success",0.95,{"agents":len(self.ctx.results)},report)
