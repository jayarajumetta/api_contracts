from qaira_semantic_compiler.core.context import AgentResult
import re
class SchemaAttachmentAgent:
    name="SchemaAttachmentAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        schemas=self.ctx.state.get("schemas",[]); attached=0; items=[]
        for r in self.ctx.state.get("routes",[]):
            if r.get("requestBody") and r["requestBody"].get("properties"): continue
            tokens=set(re.findall(r"[A-Za-z0-9]+", r["path"].lower()))
            best=None; score=0
            for s in schemas:
                st=set(re.findall(r"[A-Za-z0-9]+",s["name"].lower()))
                sc=len(tokens & st)/max(len(tokens|st),1) if st else 0
                if sc>score: best=s; score=sc
            if best and score>=0.18:
                r["requestBody"]={"type":"object","properties":{},"schemaRef":best["name"],"source":"schema_attachment"}
                attached+=1; items.append({"routeId":r["id"],"schema":best["name"],"score":score})
        self.ctx.write_json("validation/schema_attachment.json", {"attached":attached,"items":items})
        return AgentResult(self.name,"success",attached/max(len([r for r in self.ctx.state.get("routes",[]) if r["method"] in {"POST","PUT","PATCH"}]),1),{"attached":attached}, {})
