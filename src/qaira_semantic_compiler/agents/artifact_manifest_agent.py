from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
import hashlib

class ArtifactManifestAgent:
    name = "ArtifactManifestAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        items = []
        for p in self.ctx.output.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(self.ctx.output)).replace("\\", "/")
                try:
                    digest = hashlib.sha256(p.read_bytes()).hexdigest()
                except Exception:
                    digest = ""
                items.append({"file": rel, "size": p.stat().st_size, "sha256": digest})
        manifest = {"count": len(items), "items": sorted(items, key=lambda x: x["file"])}
        self.ctx.write_json("runtime/artifact_manifest.json", manifest)
        return AgentResult(self.name, "success", 0.95 if items else 0.2, {"count": len(items)}, manifest)
