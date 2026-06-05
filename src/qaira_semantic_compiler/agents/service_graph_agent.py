from qaira_semantic_compiler.core.context import AgentResult
import re
class ServiceGraphAgent:
    name="ServiceGraphAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        by={(i["file"],i["local"]):i for i in self.ctx.state.get("imports",[])}
        edges=[]
        for r in self.ctx.state.get("routes",[]):
            h=r.get("handler","")
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*\(",h):
                im=by.get((r["file"],m.group(1)))
                edges.append({"from":r["id"],"local":m.group(1),"method":m.group(2),"toFile":im.get("resolvedFile","") if im else "","confidence":0.85 if im and im.get("resolvedFile") else 0.4})
        self.ctx.state["serviceEdges"]=edges
        self.ctx.write_json("graph/service_graph.json", {"count":len(edges),"resolved":len([e for e in edges if e["toFile"]]),"items":edges})
        return AgentResult(self.name,"success",0.9 if edges else 0.2,{"edges":len(edges),"resolved":len([e for e in edges if e["toFile"]])}, {})
