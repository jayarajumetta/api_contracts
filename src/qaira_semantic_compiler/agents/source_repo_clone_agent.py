from qaira_semantic_compiler.core.context import AgentResult
from pathlib import Path
from urllib.parse import quote
import os, shutil, subprocess

class SourceRepoCloneAgent:
    name = "SourceRepoCloneAgent"
    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger
        self.commands = []
    def run(self):
        cfg = self.ctx.config.get("repository_input", {}) or {}
        repo_url = cfg.get("repo_url") or os.environ.get(cfg.get("repo_url_env", "QAIRA_REPO_URL"), "") or os.environ.get("PUBLIC_REPO_URL", "") or os.environ.get("GIT_REPO_URL", "")
        branch = cfg.get("branch") or os.environ.get("QAIRA_REPO_BRANCH", "")
        clone_dir = Path(cfg.get("clone_dir", "/workspace/source-repo"))
        token = os.environ.get(cfg.get("token_env", "GIT_TOKEN"), "")
        username = os.environ.get(cfg.get("username_env", "GIT_USERNAME"), "")
        report = {"enabled": bool(cfg.get("enabled", True)), "repoUrlProvided": bool(repo_url), "repoUrl": self.redact(repo_url, token), "branch": branch or "default", "cloneDir": str(clone_dir), "cloned": False, "sourceDirBefore": str(self.ctx.source), "sourceDirAfter": str(self.ctx.source)}
        if not cfg.get("enabled", True):
            report["reason"] = "repository_input_disabled_using_mounted_source"
            self.ctx.write_json("repo/source_repo_clone_report.json", report)
            return AgentResult(self.name, "success", 0.9, report, report)
        if not repo_url:
            report["reason"] = "repo_url_missing_using_mounted_source"
            self.ctx.write_json("repo/source_repo_clone_report.json", report)
            return AgentResult(self.name, "success", 0.75, report, report)
        try:
            if clone_dir.exists(): shutil.rmtree(clone_dir)
            clone_dir.parent.mkdir(parents=True, exist_ok=True)
            auth_url = self.auth_url(repo_url, token, username)
            cmd = ["git", "clone", "--depth", "1"]
            if branch: cmd += ["--branch", branch]
            cmd += [auth_url, str(clone_dir)]
            result = self.run_cmd(cmd, redact_token=token, timeout=600)
            if result["returncode"] != 0:
                report.update({"reason":"git_clone_failed","returncode":result["returncode"],"stdout":result.get("stdout","")[-2000:],"stderr":result.get("stderr","")[-4000:],"sourceDirAfter":str(self.ctx.source)})
                self.ctx.write_json("repo/source_repo_clone_report.json", report)
                return AgentResult(self.name, "failed_open", 0.25, report, report)
            self.ctx.source = clone_dir
            self.ctx.state["inputRepoUrl"] = repo_url
            self.ctx.state["inputRepoCloneDir"] = str(clone_dir)
            report.update({"cloned": True, "reason": "source_repo_cloned_and_selected", "sourceDirAfter": str(self.ctx.source)})
            self.ctx.write_json("repo/source_repo_clone_report.json", report)
            return AgentResult(self.name, "success", 0.95, report, report)
        except Exception as e:
            report.update({"reason":"git_clone_exception","error":str(e),"sourceDirAfter":str(self.ctx.source)})
            self.ctx.write_json("repo/source_repo_clone_report.json", report)
            return AgentResult(self.name, "failed_open", 0.25, report, report)
    def auth_url(self, repo_url, token, username):
        if token and repo_url.startswith("https://"):
            return repo_url.replace("https://", f"https://{quote(username or 'x-access-token', safe='')}:{quote(token, safe='')}@")
        return repo_url
    def run_cmd(self, cmd, redact_token="", timeout=120):
        env=os.environ.copy(); env["GIT_TERMINAL_PROMPT"]="0"
        safe_cmd=[self.redact(c, redact_token) for c in cmd]
        p=subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        item={"cmd":safe_cmd,"returncode":p.returncode,"stdout":self.redact(p.stdout, redact_token),"stderr":self.redact(p.stderr, redact_token)}
        self.commands.append(item)
        self.ctx.write_json("repo/source_repo_clone_command_log.json", {"commands": self.commands})
        return item
    def redact(self, text, token):
        if text is None: return ""
        text=str(text)
        if token: text=text.replace(token,"<redacted>").replace(quote(token,safe=""),"<redacted>")
        return text
