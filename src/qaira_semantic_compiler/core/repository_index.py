from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import fnmatch, json, re

class RepositoryIndex:
    def __init__(self, source: Path, cfg: Dict[str, Any]):
        self.source = Path(source)
        self.cfg = cfg or {}
        self.exclude_dirs = set((cfg.get("scan") or {}).get("exclude_dirs", []))
        self.exclude_files = (cfg.get("scan") or {}).get("exclude_files", [])
        self.max_file_size = int((cfg.get("scan") or {}).get("max_file_size_kb", 4096)) * 1024
        self.files: List[Path] = []
        self.by_basename: Dict[str, List[str]] = {}
        self.services: Dict[str, List[str]] = {}
        self.dtos: Dict[str, List[str]] = {}
        self.schemas: Dict[str, List[str]] = {}
        self.controllers: Dict[str, List[str]] = {}

    def skip(self, p: Path) -> bool:
        parts = set(p.parts)
        if parts & self.exclude_dirs:
            return True
        if p.is_file():
            if p.stat().st_size > self.max_file_size:
                return True
            for pat in self.exclude_files:
                if fnmatch.fnmatch(p.name, pat):
                    return True
        return False

    def build(self):
        for p in self.source.rglob("*"):
            if self.skip(p) or not p.is_file():
                continue
            rel = str(p.relative_to(self.source)).replace("\\", "/")
            self.files.append(p)
            self.by_basename.setdefault(p.name, []).append(rel)
            stem = p.stem.lower()
            if "service" in stem:
                self.services.setdefault(stem, []).append(rel)
            if any(x in stem for x in ["dto", "schema", "validator"]):
                self.dtos.setdefault(stem, []).append(rel)
                self.schemas.setdefault(stem, []).append(rel)
            if any(x in stem for x in ["route", "controller"]):
                self.controllers.setdefault(stem, []).append(rel)
        return self

    def resolve_by_basename(self, name: str):
        candidates = []
        stem = Path(name).name
        for key, vals in self.by_basename.items():
            if key == stem or key.startswith(stem + ".") or key.startswith(stem):
                candidates.extend(vals)
        return candidates

    def to_dict(self):
        return {
            "fileCount": len(self.files),
            "services": self.services,
            "dtos": self.dtos,
            "schemas": self.schemas,
            "controllers": self.controllers,
            "basenameCount": len(self.by_basename),
        }
