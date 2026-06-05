from qaira_semantic_compiler.core.context import AgentResult

class CodeDeltaGenerationAgent:
    name="CodeDeltaGenerationAgent"
    def __init__(self,ctx,logger):
        self.ctx=ctx
        self.logger=logger
    def run(self):
        review=self.ctx.state.get("llmIterationReview") or self.ctx.read_json("analysis/iteration_llm_review.json",{}) or {}
        deltas=review.get("suggestedAgentDeltas") or []
        safe=[]
        blocked=[]
        allowed_agents={
            "RouteDiscoveryAgent","BodyDiscoveryAgent","ServiceGraphAgent","ServiceBodyFieldAgent",
            "DbWriteFieldAgent","SchemaAttachmentAgent","InferredSchemaRegistryAgent","TestGenerationAgent",
            "QualityGateAgent"
        }
        for d in deltas:
            agent=d.get("agentName") or d.get("agent") or ""
            if agent in allowed_agents and float(d.get("confidence",0.5) or 0.5)>=0.6:
                safe.append(d)
            else:
                blocked.append({"delta":d,"reason":"agent_not_allowed_or_low_confidence"})
        report={"mode":"safe_delta_plan","safeDeltas":safe,"blockedDeltas":blocked,"appliedCodeChanges":0,"reason":"runtime does not self-modify code unless deterministic patch library is implemented"}
        self.ctx.write_json("codegen/llm_delta_patch_plan.json",report)
        return AgentResult(self.name,"success",0.85,{"safeDeltas":len(safe),"blockedDeltas":len(blocked)},report)
