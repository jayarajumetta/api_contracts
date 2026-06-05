from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
import time, traceback, signal

class TimeoutError(Exception): pass

class AgentRunner:
    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def _timeout(self, signum, frame):
        raise TimeoutError("agent timeout")

    def run(self, agent):
        name = agent.name
        self.logger.log("START", name, "started")
        start = time.time()
        timeout = int((self.ctx.config.get("runtime") or {}).get("agent_timeout_seconds", 900))
        fail_open = bool((self.ctx.config.get("runtime") or {}).get("fail_open", True))
        old = signal.signal(signal.SIGALRM, self._timeout)
        signal.alarm(timeout if timeout > 0 else 0)
        try:
            result = agent.run()
            if not isinstance(result, AgentResult):
                result = AgentResult(name=name, status="success", confidence=0.8, outputs={"raw": result})
            result.finish()
            self.logger.log("END", name, "completed", status=result.status, confidence=result.confidence, seconds=round(time.time()-start,2))
        except Exception as e:
            self.logger.error(name, e)
            result = AgentResult(
                name=name,
                status="failed_open" if fail_open else "failed",
                confidence=0.0,
                errors=[{"message": str(e), "traceback": traceback.format_exc()}]
            ).finish()
            if not fail_open:
                raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
        self.ctx.results.append(result)
        self.ctx.write_json(f"agents/{name}/result.json", result.__dict__)
        return result
