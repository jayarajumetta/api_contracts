from qaira_semantic_compiler.core.context import AgentResult
import re
class BodyDiscoveryAgent:
    name="BodyDiscoveryAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        routes=self.ctx.state.get("routes",[]); details=[]; detected=0; fields_known=0
        for r in routes:
            h=r.get("handler","")
            aliases=set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:req|request)\.body",h))
            if re.search(r"(?:req|request)\.body",h): aliases.add("body")
            aliases |= {"payload","data","input","dto","requestBody"}
            fields=set()
            for a in aliases:
                fields |= set(re.findall(r"\b"+re.escape(a)+r"\.([A-Za-z_$][\w$]*)",h))
                for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:req|request)\.body",h):
                    for part in m.group(1).split(","):
                        name=part.strip().split(":")[0].strip()
                        if re.match(r"^[A-Za-z_$][\w$]*$",name): fields.add(name)
            has_body = bool(re.search(r"(?:req|request)\.body|payload|dto|requestBody",h))
            if has_body: detected+=1
            if fields: fields_known+=1
            details.append({"routeId":r["id"],"hasBody":has_body,"fields":sorted(fields),"aliases":sorted(aliases)})
            r["requestBody"]={"type":"object","properties":{f:{"type":"string","source":"body_discovery"} for f in sorted(fields)}} if fields else None
        self.ctx.state["bodyDetails"]=details
        self.ctx.write_json("discovery/body_discovery.json", {"detected":detected,"fieldsKnown":fields_known,"items":details})
        return AgentResult(self.name,"success",detected/max(len([r for r in routes if r["method"] in {"POST","PUT","PATCH"}]),1),{"detected":detected,"fieldsKnown":fields_known}, {})
