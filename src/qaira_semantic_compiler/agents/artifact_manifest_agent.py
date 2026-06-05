from qaira_semantic_compiler.core.context import AgentResult
import hashlib
class ArtifactManifestAgent:
    name="ArtifactManifestAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        items=[]
        for p in self.ctx.output.rglob("*"):
            if p.is_file():
                rel=str(p.relative_to(self.ctx.output)).replace("\\","/")
                items.append({"file":rel,"size":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
        self.ctx.write_json("runtime/artifact_manifest.json",{"count":len(items),"items":items})
        return AgentResult(self.name,"success",0.95,{"artifacts":len(items)}, {})
