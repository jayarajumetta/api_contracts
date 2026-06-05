from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
import json, os, time, traceback, hashlib, datetime

def now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

@dataclass
class AgentResult:
    name: str
    status: str
    confidence: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=now_iso)
    ended_at: str = ""

    def finish(self):
        self.ended_at = now_iso()
        return self

@dataclass
class RunContext:
    source: Path
    output: Path
    learning: Path
    config: Dict[str, Any]
    changed_files: str = ""
    iteration: int = 1
    agent_results: List[AgentResult] = field(default_factory=list)

    def path(self, rel: str) -> Path:
        p = self.output / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_json(self, rel: str, obj: Any):
        p = self.path(rel)
        p.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
        return p

    def write_text(self, rel: str, text: str):
        p = self.path(rel)
        p.write_text(text, encoding="utf-8")
        return p
