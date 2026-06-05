from qaira_semantic_compiler.core.context import AgentResult
class LLMGatewayAgent:
    name="LLMGatewayAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        # Fail-open by design. No blocking network call unless explicitly implemented later.
        report={"enabled":bool(self.ctx.config.get("llm",{}).get("enabled")),"mode":"selective_fail_open","networkCallsExecuted":0}
        self.ctx.write_json("llm/llm_gateway_report.json",report)
        return AgentResult(self.name,"success",0.9,report,report)
