from qaira_semantic_compiler.core.context import AgentResult
class ContractBuilderAgent:
    name="ContractBuilderAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        contracts=[]
        for r in self.ctx.state.get("routes",[]):
            contracts.append({
                "id":r["id"],"method":r["method"],"path":r["path"],"file":r["file"],"line":r["line"],
                "parameters":r.get("parameters",[]),
                "requestBody":r.get("requestBody"),
                "responseBody":r.get("responseBody"),
                "confidence":0.9 if r.get("requestBody") or r["method"]=="GET" else 0.55
            })
        self.ctx.state["contracts"]=contracts
        self.ctx.write_json("discovery/unified_api_contracts.json", {"contracts":contracts})
        return AgentResult(self.name,"success",0.95 if contracts else 0.0,{"contracts":len(contracts)}, {})
