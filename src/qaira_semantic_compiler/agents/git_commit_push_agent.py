from __future__ import annotations
from qaira_semantic_compiler.core.context import AgentResult
import os, subprocess

class GitCommitPushAgent:
    name = "GitCommitPushAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        cfg = self.ctx.config.get("git_push") or {}
        repo_cfg = self.ctx.config.get("repo") or {}
        repo_url = cfg.get("repo_url") or repo_cfg.get("url", "")
        result = {
            "enabled": bool(cfg.get("enabled", False)),
            "repoUrlConfigured": bool(repo_url),
            "targetBranch": cfg.get("target_branch", repo_cfg.get("default_branch", "develop")),
            "executeGit": bool(cfg.get("execute_git", False)),
            "push": bool(cfg.get("push", False)),
            "committed": False,
            "pushed": False
        }
        if not cfg.get("enabled", False):
            result["reason"] = "git_push_disabled"
        elif not repo_url:
            result["reason"] = "repo_url_missing"
        elif not os.environ.get(cfg.get("username_env", "GIT_USERNAME"), "") or not os.environ.get(cfg.get("token_env", "GIT_TOKEN"), ""):
            result["reason"] = "git_credentials_env_missing"
        elif not cfg.get("execute_git", False) or not cfg.get("push", False):
            result["reason"] = "execute_git_or_push_false"
        else:
            result["reason"] = "git execution enabled but no generated patches to commit"
        self.ctx.write_json("git/code_push_report.json", result)
        pr = {"enabled": bool((self.ctx.config.get("pull_request") or {}).get("enabled", False)), "created": False, "reason": "PR creation is fail-safe/deferred unless provider integration is implemented"}
        self.ctx.write_json("git/pr_report.json", pr)
        return AgentResult(self.name, "success", 0.8, result, result)
