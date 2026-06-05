from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
import json, datetime, hashlib, traceback, time

def now():
    return datetime.datetime.utcnow().isoformat() + "Z"

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

@dataclass
class AgentResult:
    name: str
    status: str = "success"
    confidence: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=now)
    ended_at: str = ""

    def finish(self):
        self.ended_at = now()
        return self

@dataclass
class RunContext:
    source: Path
    output: Path
    learning: Path
    config: Dict[str, Any]
    state: Dict[str, Any] = field(default_factory=dict)
    results: List[AgentResult] = field(default_factory=list)

    def out(self, rel: str) -> Path:
        p = self.output / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_json(self, rel: str, obj: Any):
        p = self.out(rel)
        p.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
        return p

    def read_json(self, rel: str, default=None):
        p = self.output / rel
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))

    def write_text(self, rel: str, text: str):
        p = self.out(rel)
        p.write_text(text, encoding="utf-8")
        return p
