from __future__ import annotations
from pathlib import Path
import json, datetime, traceback, re

SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+", re.I),
]

def ts():
    return datetime.datetime.utcnow().isoformat() + "Z"

class Logger:
    def __init__(self, output: Path, console=True):
        self.output = Path(output)
        self.console_enabled = console
        (self.output / "verbose").mkdir(parents=True, exist_ok=True)

    def redact(self, text: str) -> str:
        for pat in SECRET_PATTERNS:
            text = pat.sub(r"\1=<redacted>", text)
        return text

    def log(self, level, stage, message, **kwargs):
        payload = {"ts": ts(), "level": level, "stage": stage, "message": self.redact(str(message)), **kwargs}
        with (self.output / "verbose" / "trace.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
        if self.console_enabled:
            extra = f" {json.dumps(kwargs, default=str)[:500]}" if kwargs else ""
            print(f"[Qaira][{level}] {stage}: {payload['message']}{extra}", flush=True)

    def error(self, stage, exc):
        self.log("ERROR", stage, str(exc), traceback=traceback.format_exc()[-4000:])
