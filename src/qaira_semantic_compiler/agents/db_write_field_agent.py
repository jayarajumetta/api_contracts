from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.jsparse import object_keys
import re

BAD={"where","data","include","select","id","createdAt","updatedAt","deletedAt"}

class DbWriteFieldAgent:
    name="DbWriteFieldAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        idx=self.ctx.state["index"]
        patterns=[]
        by_route={}

        for edge in self.ctx.state.get("serviceEdges",[]):
            route_id=edge.get("from")
            service_file=edge.get("toFile")
            if not service_file:
                continue
            try:
                text=idx.read(service_file)
            except Exception:
                continue

            fields=self.extract_db_write_fields(text)
            fields={f for f in fields if f not in BAD and not f.startswith("_")}
            if fields:
                patterns.append({"routeId":route_id,"serviceFile":service_file,"fields":sorted(fields),"confidence":0.72})
                by_route.setdefault(route_id,set()).update(fields)

        self.ctx.state["dbWriteFieldsByRoute"]={k:sorted(v) for k,v in by_route.items()}
        self.ctx.write_json("patterns/db_write_field_patterns.json",{"count":len(patterns),"routes":len(by_route),"items":patterns})
        return AgentResult(self.name,"success" if patterns else "failed_open",0.75 if patterns else 0.25,{"patterns":len(patterns),"routes":len(by_route)},{})

    def extract_db_write_fields(self,text):
        fields=set()

        # SQL INSERT INTO table (a,b,c)
        for m in re.finditer(r"insert\s+into\s+[A-Za-z0-9_\"`.\[\]]+\s*\(([^)]+)\)",text,re.I):
            for col in m.group(1).split(","):
                c=col.strip().strip('"`[] ')
                if re.match(r"^[A-Za-z_][\w$]*$",c):
                    fields.add(c)

        # SQL UPDATE table SET a=?, b=?
        for m in re.finditer(r"update\s+[A-Za-z0-9_\"`.\[\]]+\s+set\s+([\s\S]{0,1000}?)(?:\s+where|\s+returning|[`'\"]|;)",text,re.I):
            for km in re.finditer(r"\b([A-Za-z_][\w$]*)\s*=",m.group(1)):
                fields.add(km.group(1))

        # Prisma style data object
        for m in re.finditer(r"\bdata\s*:\s*\{([\s\S]{0,3000}?)\}",text):
            fields |= object_keys(m.group(1))

        # Knex/repo style object writes
        for m in re.finditer(r"\.(?:insert|update|create|save|upsert)\s*\(\s*\{([\s\S]{0,3000}?)\}\s*\)",text):
            fields |= object_keys(m.group(1))

        return fields
