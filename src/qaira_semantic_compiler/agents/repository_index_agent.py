from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.repository_index import RepositoryIndex

class RepositoryIndexAgent:
    name = "RepositoryIndexAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        idx = RepositoryIndex(self.ctx.source, self.ctx.config).build()
        self.ctx.repository_index = idx
        data = idx.to_dict()
        self.ctx.write_json("repository/repository_index_v59.json", data)
        confidence = 0.95 if data["fileCount"] > 0 else 0.0
        return AgentResult(self.name, "success" if confidence else "failed", confidence, data, {"index": data})
