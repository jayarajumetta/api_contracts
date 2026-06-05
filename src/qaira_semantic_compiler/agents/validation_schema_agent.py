from qaira_semantic_compiler.core.context import AgentResult
import re

class ValidationSchemaAgent:
    name="ValidationSchemaAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        idx=self.ctx.state["index"]
        schemas=[]
        seen=set()

        for p in idx.files:
            rel=str(p.relative_to(idx.source)).replace("\\","/")
            if not rel.endswith((".js",".jsx",".ts",".tsx",".py",".java",".cs")):
                continue
            try:
                txt=idx.read(rel)
            except Exception:
                continue

            patterns=[
                r"(?:const|export\s+const)\s+([A-Za-z_$][\w$]*(?:Schema|Validator|Validation|Dto|DTO))\s*=",
                r"(?:class|interface|type)\s+([A-Za-z_$][\w$]*(?:Dto|DTO|Schema|Request|Payload))\b",
                r"([A-Za-z_$][\w$]*)\s*:\s*z\.object\s*\(",
                r"(?:const|export\s+const)\s+([A-Za-z_$][\w$]*)\s*=\s*z\.object\s*\(",
                r"(?:const|export\s+const)\s+([A-Za-z_$][\w$]*)\s*=\s*Joi\.object\s*\(",
                r"(?:const|export\s+const)\s+([A-Za-z_$][\w$]*)\s*=\s*yup\.object\s*\("
            ]

            for pat in patterns:
                for m in re.finditer(pat,txt):
                    name=m.group(1)
                    key=(rel,name)
                    if key in seen:
                        continue
                    seen.add(key)
                    schemas.append({
                        "name":name,
                        "file":rel,
                        "line":txt.count("\n",0,m.start())+1
                    })

        self.ctx.state["schemas"]=schemas
        self.ctx.write_json("validation/schemas.json", {"count":len(schemas),"items":schemas})
        return AgentResult(self.name,"success",0.9 if schemas else 0.2,{"schemas":len(schemas)}, {})
