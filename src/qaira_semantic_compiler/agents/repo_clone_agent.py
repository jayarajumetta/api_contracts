from __future__ import annotations
from pathlib import Path
from qaira_semantic_compiler.core.context import AgentResult
import os, subprocess, shutil

class RepoCloneAgent:
    name = "RepoCloneAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        cfg = self.ctx.config.get("repo") or {}
        if not cfg.get("enabled", False):
            self.ctx.write_json("git/repo_clone_report.json", {"enabled": False, "sourceDir": str(self.ctx.source), "reason": "repo_clone_disabled"})
            return AgentResult(self.name, "success", 1.0, {"enabled": False}, {"sourceDir": str(self.ctx.source)})
        url = cfg.get("url", "")
        execute = bool(cfg.get("execute_git", False))
        clone_dir = Path(cfg.get("clone_dir", "/workspace/repo"))
        branch = cfg.get("default_branch", "develop")
        username = os.environ.get(cfg.get("username_env", "GIT_USERNAME"), "")
        token = os.environ.get(cfg.get("token_env", "GIT_TOKEN"), "")
        report = {"enabled": True, "urlConfigured": bool(url), "executeGit": execute, "cloneDir": str(clone_dir), "branch": branch, "cloned": False}
        if not url:
            report["reason"] = "repo_url_missing"
        elif not username or not token:
            report["reason"] = "git_credentials_env_missing"
        elif not execute:
            report["reason"] = "execute_git_false_safe_plan_only"
        else:
            if clone_dir.exists() and cfg.get("clean_clone", True):
                shutil.rmtree(clone_dir)
            clone_url = url.replace("https://", f"https://{username}:{token}@")
            subprocess.run(["git", "clone", "--branch", branch, clone_url, str(clone_dir)], check=True, timeout=600)
            report["cloned"] = True
            src_sub = cfg.get("source_subdir") or ""
            self.ctx.source = clone_dir / src_sub if src_sub else clone_dir
            report["sourceDir"] = str(self.ctx.source)
        self.ctx.write_json("git/repo_clone_report.json", report)
        conf = 1.0 if report.get("cloned") or not cfg.get("enabled") else 0.5
        return AgentResult(self.name, "success", conf, report, report)
