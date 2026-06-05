from qaira_semantic_compiler.core.context import AgentResult
import re

class DbWriteFieldAgent:
    name="DbWriteFieldAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        idx=self.ctx.state["index"]
        edges=self.ctx.state.get("serviceEdges",[])
        patterns=[]
        by_route={}

        for edge in edges:
            route_id=edge.get("from")
            service_file=edge.get("toFile")
            if not service_file:
                continue
            try:
                text=idx.read(service_file)
            except Exception:
                continue
            fields=self.extract_db_write_fields(text)
            if fields:
                patterns.append({"routeId":route_id,"serviceFile":service_file,"fields":sorted(fields),"confidence":0.68})
                by_route.setdefault(route_id,set()).update(fields)

        self.ctx.state["dbWriteFieldsByRoute"]={k:sorted(v) for k,v in by_route.items()}
        self.ctx.write_json("patterns/db_write_field_patterns.json",{
            "count":len(patterns),
            "routes":len(by_route),
            "items":patterns
        })
        return AgentResult(self.name,"success" if patterns else "failed_open",0.7 if patterns else 0.25,{"patterns":len(patterns),"routes":len(by_route)},{})

    def extract_db_write_fields(self,text):
        fields=set()
        # Prisma style: prisma.user.create({ data: { a, b: value }})
        for m in re.finditer(r"\.(?:create|update|upsert)\s*\(\s*\{[\s\S]{0,1000}?\bdata\s*:\s*\{([\s\S]{0,2000}?)\}",text):
            obj=m.group(1)
            fields |= self.object_keys(obj)
        # Knex/SQL builder style: insert({ a: ..., b: ... })
        for m in re.finditer(r"\.(?:insert|update)\s*\(\s*\{([\s\S]{0,2000}?)\}\s*\)",text):
            fields |= self.object_keys(m.group(1))
        # Generic repository.create({ a: ... })
        for m in re.finditer(r"\.(?:create|save)\s*\(\s*\{([\s\S]{0,2000}?)\}\s*\)",text):
            fields |= self.object_keys(m.group(1))
        return fields

    def object_keys(self,obj):
        out=set()
        for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*:",obj):
            key=m.group(1)
            if key not in {"where","data","include","select","id","createdAt","updatedAt"}:
                out.add(key)
        return out
