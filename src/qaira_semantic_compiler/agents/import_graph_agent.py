from qaira_semantic_compiler.core.context import AgentResult
import re
class ImportGraphAgent:
    name="ImportGraphAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        idx=self.ctx.state["index"]; imports=[]
        files=set([r["file"] for r in self.ctx.state.get("routes",[])]) | set(idx.by_kind["services"])
        for rel in files:
            try: txt=idx.read(rel)
            except Exception: continue
            for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\(['\"]([^'\"]+)['\"]\)",txt):
                imports.append({"file":rel,"local":m.group(1),"module":m.group(2),"resolvedFile":idx.resolve_module(rel,m.group(2))})
            for m in re.finditer(r"import\s+([A-Za-z_$][\w$]*)\s+from\s+['\"]([^'\"]+)['\"]",txt):
                imports.append({"file":rel,"local":m.group(1),"module":m.group(2),"resolvedFile":idx.resolve_module(rel,m.group(2))})
        self.ctx.state["imports"]=imports
        self.ctx.write_json("graph/import_graph.json", {"count":len(imports),"resolved":len([i for i in imports if i.get("resolvedFile")]),"items":imports})
        return AgentResult(self.name,"success",0.9 if imports else 0.3,{"imports":len(imports),"resolved":len([i for i in imports if i.get("resolvedFile")])}, {})
