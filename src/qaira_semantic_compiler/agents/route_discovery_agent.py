from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.parser import extract_route_calls
class RouteDiscoveryAgent:
    name="RouteDiscoveryAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        idx=self.ctx.state["index"]; routes=[]
        for rel in idx.by_kind["routes"] + [r for r in idx.by_kind["controllers"] if r not in idx.by_kind["routes"]]:
            if not rel.endswith((".js",".jsx",".ts",".tsx")): continue
            txt=idx.read(rel)
            for c in extract_route_calls(txt):
                rid=f"{c['method'].lower()}-{c['path'].strip('/').replace('/','-').replace('{','').replace('}','') or 'root'}"
                routes.append({"id":rid,"method":c["method"],"path":c["path"],"file":rel,"line":c["line"],"handler":c["handler"],"call":c["call"],"parser":"balanced"})
        # fallback scan all js/ts if route folder missed
        seen={(r["file"],r["line"],r["method"],r["path"]) for r in routes}
        for p in idx.files:
            rel=str(p.relative_to(idx.source)).replace("\\","/")
            if not rel.endswith((".js",".jsx",".ts",".tsx")) or rel in idx.by_kind["routes"]: continue
            txt=idx.read(rel)
            for c in extract_route_calls(txt):
                key=(rel,c["line"],c["method"],c["path"])
                if key in seen: continue
                rid=f"{c['method'].lower()}-{c['path'].strip('/').replace('/','-').replace('{','').replace('}','') or 'root'}"
                routes.append({"id":rid,"method":c["method"],"path":c["path"],"file":rel,"line":c["line"],"handler":c["handler"],"call":c["call"],"parser":"balanced"})
        self.ctx.state["routes"]=routes
        self.ctx.write_json("discovery/routes.json", {"count":len(routes),"items":routes})
        return AgentResult(self.name,"success",0.98 if routes else 0.0,{"routes":len(routes)},{"routes":routes})
