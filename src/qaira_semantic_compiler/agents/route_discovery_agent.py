from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.parser import extract_route_calls

class RouteDiscoveryAgent:
    name="RouteDiscoveryAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        idx=self.ctx.state["index"]
        routes=[]
        seen=set()

        candidate_files = []
        candidate_files += idx.by_kind.get("routes", [])
        candidate_files += idx.by_kind.get("controllers", [])

        # Also scan all JS/TS files as fallback, because many Fastify projects register routes in plugin files.
        for p in idx.files:
            rel=str(p.relative_to(idx.source)).replace("\\","/")
            if rel.endswith((".js",".jsx",".ts",".tsx")) and rel not in candidate_files:
                candidate_files.append(rel)

        for rel in candidate_files:
            if not rel.endswith((".js",".jsx",".ts",".tsx")):
                continue
            try:
                txt=idx.read(rel)
            except Exception:
                continue
            for c in extract_route_calls(txt):
                key=(rel,c["line"],c["method"],c["path"])
                if key in seen:
                    continue
                seen.add(key)
                path_id = c["path"].strip("/").replace("/","-").replace("{","").replace("}","").replace(":","") or "root"
                rid=f"{c['method'].lower()}-{path_id}"
                routes.append({
                    "id":rid,
                    "method":c["method"],
                    "path":c["path"],
                    "file":rel,
                    "line":c["line"],
                    "handler":c["handler"],
                    "call":c["call"],
                    "parser":"balanced"
                })

        self.ctx.state["routes"]=routes
        self.ctx.write_json("discovery/routes.json", {"count":len(routes),"items":routes})

        status="success" if routes else "failed_open"
        confidence=0.98 if routes else 0.0
        return AgentResult(self.name,status,confidence,{"routes":len(routes)},{"routes":routes})
