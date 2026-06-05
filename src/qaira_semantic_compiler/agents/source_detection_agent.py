from qaira_semantic_compiler.core.context import AgentResult
import json
class SourceDetectionAgent:
    name="SourceDetectionAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        idx=self.ctx.state["index"]
        tech={"node":False,"typescript":False,"python":False,"java":False,"dotnet":False,"frameworkHints":[]}
        for p in idx.files:
            rel=str(p.relative_to(idx.source)).replace("\\","/")
            if rel.endswith("package.json"):
                tech["node"]=True
                try:
                    pkg=json.loads(p.read_text(encoding="utf-8"))
                    deps={**pkg.get("dependencies",{}), **pkg.get("devDependencies",{})}
                    for k in deps:
                        if k in ["fastify","express","@nestjs/core","zod","joi","yup"]:
                            tech["frameworkHints"].append(k)
                except Exception: pass
            if p.suffix==".ts": tech["typescript"]=True
            if p.suffix==".py": tech["python"]=True
            if p.suffix==".java": tech["java"]=True
            if p.suffix==".cs": tech["dotnet"]=True
        self.ctx.state["source"]=tech
        self.ctx.write_json("discovery/source_detection.json", tech)
        return AgentResult(self.name,"success",0.95,tech,tech)
