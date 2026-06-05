from qaira_semantic_compiler.core.context import AgentResult
class ParamTypeDiscoveryAgent:
    name="ParamTypeDiscoveryAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        inferred=0
        for r in self.ctx.state.get("routes",[]):
            for p in r.get("parameters",[]):
                n=p["name"].lower()
                if n.endswith("id") or n=="id":
                    p["type"]="string"; p["format"]="identifier"; inferred+=1
                elif n in {"page","limit","offset","size"}:
                    p["type"]="integer"; inferred+=1
        self.ctx.write_json("discovery/param_type_discovery.json", {"inferred":inferred})
        return AgentResult(self.name,"success",0.85,{"inferred":inferred},{})
