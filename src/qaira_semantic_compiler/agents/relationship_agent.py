from qaira_semantic_compiler.core.context import AgentResult
class RelationshipAgent:
    name="RelationshipAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        order={"POST":1,"GET":2,"PUT":3,"PATCH":4,"DELETE":5}
        seq=sorted(self.ctx.state.get("contracts",[]), key=lambda c:(c["path"].split("/")[1:3],order.get(c["method"],9)))
        self.ctx.state["sequence"]=seq
        self.ctx.write_json("testing/request_sequence_plan.json", {"confidence":0.75,"sequence":[{"id":c["id"],"method":c["method"],"path":c["path"]} for c in seq]})
        return AgentResult(self.name,"success",0.75,{"sequence":len(seq)}, {})
