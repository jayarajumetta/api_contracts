from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.llm_client import LLMClient

class IterationLLMReviewerAgent:
    name="IterationLLMReviewerAgent"
    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger
    def run(self):
        context=self.ctx.read_json("runtime/iteration_context.json",{}) or {}
        best=context.get("best") or {}
        quality=self.ctx.read_json("quality/quality_gate_report.json",{}) or {}
        threshold=float((self.ctx.config.get("auto_iteration") or self.ctx.config.get("agentic_runtime") or {}).get("min_score_percent", (self.ctx.config.get("auto_iteration") or {}).get("quality_threshold_percent",90)))
        only_below=bool((self.ctx.config.get("enterprise_loop") or {}).get("llm_only_when_below_threshold", True))
        score=float(quality.get("score", best.get("score",0)) or 0)
        if only_below and score>=threshold:
            result={"skipped":True,"reason":"score_meets_threshold","score":score,"threshold":threshold}
        else:
            result=LLMClient(self.ctx,self.logger).review("IterationLLMReviewerAgent",context,default={"accepted":score>=threshold,"score":score,"suggestedAgentDeltas":[]})
        self.ctx.state["llmIterationReview"]=result
        self.ctx.write_json("analysis/iteration_llm_review.json",result)
        return AgentResult(self.name,"success",0.9,{"score":score,"llmSkipped":result.get("skipped",False)},result)
