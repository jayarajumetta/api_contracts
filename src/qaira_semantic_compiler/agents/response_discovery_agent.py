from qaira_semantic_compiler.core.context import AgentResult
import re
class ResponseDiscoveryAgent:
    name="ResponseDiscoveryAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        count=0
        for r in self.ctx.state.get("routes",[]):
            h=r.get("handler","")
            vars=set(re.findall(r"(?:reply|res|response)\.(?:send|json)\s*\(\s*([A-Za-z_$][\w$]*)",h))
            vars |= set(re.findall(r"return\s+([A-Za-z_$][\w$]*)",h))
            r["responseBody"]={"type":"object","properties":{"id":{"type":"string"}},"responseVars":sorted(vars)}
            if vars: count+=1
        self.ctx.write_json("discovery/response_discovery.json", {"routesWithResponseVars":count})
        return AgentResult(self.name,"success",0.9 if count else 0.4,{"routesWithResponseVars":count}, {})
