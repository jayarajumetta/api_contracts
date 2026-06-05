from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.fs_index import RepositoryIndex
class RepositoryIndexAgent:
    name="RepositoryIndexAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        idx=RepositoryIndex(self.ctx.source,self.ctx.config).build()
        self.ctx.state["index"]=idx
        summary=idx.summary()
        self.ctx.write_json("repository/index.json", summary)
        return AgentResult(self.name,"success",0.95 if summary["fileCount"] else 0.0,summary,summary)
