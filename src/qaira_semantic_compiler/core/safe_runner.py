from __future__ import annotations
from typing import Callable, Any
from .context import AgentResult, now_iso
import traceback, time

class SafeAgentRunner:
    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self, name: str, fn: Callable[[], AgentResult], fail_open: bool=True) -> AgentResult:
        self.logger.console("START", name, "started")
        started = time.time()
        try:
            result = fn()
            if not isinstance(result, AgentResult):
                result = AgentResult(name=name, status="success", confidence=0.8, outputs={"raw": result})
            result.finish()
            self.logger.console("END", name, "completed", status=result.status, confidence=result.confidence, durationSeconds=round(time.time()-started,2))
            self.ctx.agent_results.append(result)
            self.ctx.write_json(f"agents/{name}/result.json", result.__dict__)
            return result
        except Exception as e:
            self.logger.exception(name, e)
            result = AgentResult(
                name=name,
                status="failed_open" if fail_open else "failed",
                confidence=0.0,
                errors=[{"message": str(e), "traceback": traceback.format_exc()}],
            ).finish()
            self.ctx.agent_results.append(result)
            self.ctx.write_json(f"agents/{name}/result.json", result.__dict__)
            if not fail_open:
                raise
            return result
