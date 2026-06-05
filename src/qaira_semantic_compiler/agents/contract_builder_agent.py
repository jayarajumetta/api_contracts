from qaira_semantic_compiler.core.context import AgentResult

BODY_METHODS={"POST","PUT","PATCH"}

class ContractBuilderAgent:
    name="ContractBuilderAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        body_details={b["routeId"]:b for b in self.ctx.state.get("bodyDetails",[])}
        contracts=[]

        for r in self.ctx.state.get("routes",[]):
            request_body=r.get("requestBody")
            if r["method"] not in BODY_METHODS and not body_details.get(r["id"],{}).get("hasBody"):
                request_body=None

            contracts.append({
                "id":r["id"],
                "method":r["method"],
                "path":r["path"],
                "file":r["file"],
                "line":r["line"],
                "parameters":r.get("parameters",[]),
                "requestBody":request_body,
                "responseBody":r.get("responseBody"),
                "confidence":0.9 if request_body or r["method"]=="GET" else 0.65
            })

        self.ctx.state["contracts"]=contracts
        self.ctx.write_json("discovery/unified_api_contracts.json", {"contracts":contracts})
        return AgentResult(self.name,"success",0.95 if contracts else 0.0,{"contracts":len(contracts)}, {})
