from qaira_semantic_compiler.core.context import AgentResult
import re

class BodyDiscoveryAgent:
    name="BodyDiscoveryAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        routes=self.ctx.state.get("routes",[])
        details=[]
        detected=0
        fields_known=0

        for r in routes:
            h=r.get("handler","")
            aliases=set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:req|request)\.body",h))

            # Direct req.body usage.
            direct_body=bool(re.search(r"(?:req|request)\.body\b",h))
            if direct_body:
                aliases.add("body")

            # Common business variable names.
            aliases |= {"payload","data","input","dto","requestBody","body"}

            fields=set()

            # req.body.field direct usage.
            fields |= set(re.findall(r"(?:req|request)\.body\.([A-Za-z_$][\w$]*)",h))

            # const { a,b } = req.body
            for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:req|request)\.body",h):
                for part in m.group(1).split(","):
                    name=part.strip().split(":")[0].strip()
                    if re.match(r"^[A-Za-z_$][\w$]*$",name):
                        fields.add(name)

            # alias.field usage
            for a in aliases:
                fields |= set(re.findall(r"\b"+re.escape(a)+r"\.([A-Za-z_$][\w$]*)",h))
                for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*"+re.escape(a),h):
                    for part in m.group(1).split(","):
                        name=part.strip().split(":")[0].strip()
                        if re.match(r"^[A-Za-z_$][\w$]*$",name):
                            fields.add(name)

            # Body is present if direct req.body exists OR body alias is passed to a service call.
            body_passed_to_service=bool(re.search(r"\.\w+\s*\([^)]*(?:req|request)\.body",h))
            has_body=direct_body or body_passed_to_service

            if has_body:
                detected+=1

            if fields:
                fields_known+=1
                schema={
                    "type":"object",
                    "properties":{f:{"type":"string","source":"body_discovery"} for f in sorted(fields)},
                    "x-qaira-body-detected":True,
                    "x-qaira-fields-known":True
                }
            elif has_body:
                schema={
                    "type":"object",
                    "properties":{},
                    "additionalProperties":True,
                    "x-qaira-body-detected":True,
                    "x-qaira-fields-known":False,
                    "x-qaira-source":"body_presence_detected"
                }
            else:
                schema=None

            r["requestBody"]=schema
            details.append({
                "routeId":r["id"],
                "method":r["method"],
                "path":r["path"],
                "hasBody":has_body,
                "fieldsKnown":bool(fields),
                "fields":sorted(fields),
                "aliases":sorted(aliases)
            })

        self.ctx.state["bodyDetails"]=details
        self.ctx.write_json("discovery/body_discovery.json", {
            "detected":detected,
            "fieldsKnown":fields_known,
            "items":details
        })

        expected=len([r for r in routes if r["method"] in {"POST","PUT","PATCH"}])
        confidence=detected/max(expected,1)
        return AgentResult(
            self.name,
            "success" if detected else "failed_open",
            confidence,
            {"detected":detected,"fieldsKnown":fields_known,"expected":expected},
            {}
        )
