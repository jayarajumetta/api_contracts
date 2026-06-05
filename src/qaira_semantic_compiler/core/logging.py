from __future__ import annotations
from pathlib import Path
from typing import Any
import json, datetime, traceback, sys

def now_iso():
    return datetime.datetime.utcnow().isoformat()+"Z"

class AgentLogger:
    def __init__(self, output: Path, verbose_console: bool=True):
        self.output = Path(output)
        self.verbose_console = verbose_console
        (self.output / "verbose").mkdir(parents=True, exist_ok=True)

    def console(self, level: str, stage: str, message: str, **kwargs):
        payload = {"ts": now_iso(), "level": level, "stage": stage, "message": message, **kwargs}
        with (self.output/"verbose"/"console_progress.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str)+"\n")
        if self.verbose_console:
            extra = f" {json.dumps(kwargs, default=str)[:500]}" if kwargs else ""
            print(f"[Qaira][{level}] {stage}: {message}{extra}", flush=True)

    def jsonl(self, name: str, item: Any):
        p = self.output/"verbose"/name
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, default=str)+"\n")

    def exception(self, stage: str, exc: BaseException):
        self.console("ERROR", stage, str(exc), traceback=traceback.format_exc()[-4000:])
