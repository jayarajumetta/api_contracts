from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Any
import fnmatch, re, json

class RepositoryIndex:
    def __init__(self, source: Path, config: Dict[str, Any]):
        self.source = Path(source)
        self.config = config
        scan = config.get("scan") or {}
        self.exclude_dirs = set(scan.get("exclude_dirs", []))
        self.exclude_files = scan.get("exclude_files", [])
        self.include_ext = set(scan.get("include_extensions", []))
        self.max_size = int(scan.get("max_file_size_kb", 4096)) * 1024
        self.files: List[Path] = []
        self.text_files: List[Path] = []
        self.by_name: Dict[str, List[str]] = {}
        self.by_stem: Dict[str, List[str]] = {}
        self.by_kind: Dict[str, List[str]] = {"routes": [], "services": [], "schemas": [], "dtos": [], "repositories": []}

    def skip(self, p: Path):
        if any(part in self.exclude_dirs for part in p.parts):
            return True
        if p.is_file():
            if self.include_ext and p.suffix not in self.include_ext:
                return True
            try:
                if p.stat().st_size > self.max_size:
                    return True
            except Exception:
                return True
            for pat in self.exclude_files:
                if fnmatch.fnmatch(p.name, pat):
                    return True
        return False

    def build(self):
        for p in self.source.rglob("*"):
            if not p.is_file() or self.skip(p):
                continue
            rel = str(p.relative_to(self.source)).replace("\\", "/")
            self.files.append(p)
            self.text_files.append(p)
            self.by_name.setdefault(p.name.lower(), []).append(rel)
            self.by_stem.setdefault(p.stem.lower(), []).append(rel)
            stem = p.stem.lower()
            rel_l = rel.lower()
            if any(x in stem for x in ["route", "controller"]) or "/routes/" in rel_l:
                self.by_kind["routes"].append(rel)
            if "service" in stem or "/services/" in rel_l:
                self.by_kind["services"].append(rel)
            if any(x in stem for x in ["schema", "validator"]):
                self.by_kind["schemas"].append(rel)
            if "dto" in stem:
                self.by_kind["dtos"].append(rel)
            if "repository" in stem or "/repositories/" in rel_l:
                self.by_kind["repositories"].append(rel)
        return self

    def read(self, rel):
        return (self.source / rel).read_text(encoding="utf-8", errors="ignore")

    def resolve_module(self, from_file: str, module: str):
        if not module:
            return ""
        base = (self.source / from_file).parent
        exts = [".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"]
        if module.startswith("."):
            raw = (base / module).resolve()
            candidates = [raw] + [Path(str(raw)+e) for e in exts] + [raw/"index.js", raw/"index.ts", raw/"index.tsx"]
            for c in candidates:
                if c.exists() and c.is_file():
                    try: return str(c.relative_to(self.source)).replace("\\", "/")
                    except Exception: return str(c)
        stem = Path(module).name.lower()
        keys = [stem, stem+".js", stem+".ts", stem+".tsx"]
        for k in keys:
            vals = self.by_name.get(k) or self.by_stem.get(k)
            if vals:
                return sorted(vals, key=lambda x: (0 if "/services/" in "/"+x else 1, len(x)))[0]
        return ""

    def summary(self):
        return {"fileCount": len(self.files), "byKind": {k: len(v) for k,v in self.by_kind.items()}, "names": len(self.by_name)}
