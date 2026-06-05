from qaira_semantic_compiler.core.context import AgentResult
import re
class ValidationSchemaAgent:
    name="ValidationSchemaAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        idx=self.ctx.state["index"]; schemas=[]
        for rel in idx.by_kind["schemas"] + idx.by_kind["dtos"]:
            try: txt=idx.read(rel)
            except Exception: continue
            for m in re.finditer(r"(?:const|export\s+const|class|interface|type)\s+([A-Za-z_$][\w$]*)",txt):
                schemas.append({"name":m.group(1),"file":rel,"line":txt.count("\n",0,m.start())+1})
        self.ctx.state["schemas"]=schemas
        self.ctx.write_json("validation/schemas.json", {"count":len(schemas),"items":schemas})
        return AgentResult(self.name,"success",0.9 if schemas else 0.2,{"schemas":len(schemas)}, {})
