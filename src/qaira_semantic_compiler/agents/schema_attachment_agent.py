from qaira_semantic_compiler.core.context import AgentResult
import re

class SchemaAttachmentAgent:
    name="SchemaAttachmentAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        schemas=self.ctx.state.get("schemas",[])
        attached=0
        items=[]

        for r in self.ctx.state.get("routes",[]):
            tokens=set(re.findall(r"[A-Za-z0-9]+", r["path"].lower()))
            tokens.add(r["method"].lower())

            for e in self.ctx.state.get("serviceEdges",[]):
                if e.get("from")==r["id"] and e.get("method"):
                    tokens |= set(re.findall(r"[A-Za-z0-9]+", e["method"].lower()))

            best=None
            score=0
            for s in schemas:
                st=set(re.findall(r"[A-Za-z0-9]+",s["name"].lower()))
                sc=len(tokens & st)/max(len(tokens|st),1) if st else 0
                if sc>score:
                    best=s
                    score=sc

            # Declared schema attachment only. Inferred schema refs are handled by InferredSchemaRegistryAgent.
            if best and score>=0.10:
                if not r.get("requestBody"):
                    # Do not create body only from declared schema unless the route expects/has body.
                    if r["method"] not in {"POST","PUT","PATCH"}:
                        continue
                    r["requestBody"]={
                        "type":"object",
                        "properties":{},
                        "additionalProperties":True,
                        "x-qaira-body-detected":True,
                        "x-qaira-fields-known":False
                    }

                r["requestBody"]["declaredSchemaRef"]=best["name"]
                r["requestBody"]["declaredSchemaRefFile"]=best["file"]
                r["requestBody"]["x-qaira-declared-schema-attachment-score"]=score
                attached+=1
                items.append({"routeId":r["id"],"schema":best["name"],"file":best["file"],"score":score})

        self.ctx.state["declaredSchemaAttachments"]=items
        self.ctx.write_json("validation/declared_schema_attachment.json", {"attached":attached,"items":items})
        return AgentResult(self.name,"success" if attached else "failed_open",attached/max(len([r for r in self.ctx.state.get("routes",[]) if r["method"] in {"POST","PUT","PATCH"}]),1),{"declaredSchemaAttachments":attached}, {})
