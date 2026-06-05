from qaira_semantic_compiler.core.context import AgentResult
from pathlib import Path
import os, shutil, subprocess, datetime, json, urllib.request, re
from urllib.parse import quote

class GitFinalizationAgent:
    name="GitFinalizationAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger
        self.commands=[]

    def active_git_config(self):
        gf=self.ctx.config.get("git_finalization") or {}
        gp=self.ctx.config.get("git_push") or {}
        gg=self.ctx.config.get("git") or {}

        if gp.get("enabled",False):
            merged=dict(gf)
            merged.update(gp)
            merged["_selected_source"]="git_push_overrides_git_finalization"
            return merged
        if gf.get("enabled",False):
            gf=dict(gf); gf["_selected_source"]="git_finalization"; return gf
        if gg.get("enabled",False):
            gg=dict(gg); gg["_selected_source"]="git"; return gg

        cfg=dict(gf or gp or gg)
        cfg["_selected_source"]="none_enabled"
        return cfg

    def run(self):
        cfg=self.active_git_config()
        pr_cfg=self.ctx.config.get("pull_request") or {}
        branch_cfg=self.ctx.config.get("branch_strategy") or {}

        base_branch=branch_cfg.get("clone_base_branch") or pr_cfg.get("base_branch") or "main"
        work_branch=branch_cfg.get("work_branch") or cfg.get("target_branch") or "develop"
        push_branch=branch_cfg.get("push_work_branch") or work_branch

        report={
            "selectedConfigSource":cfg.get("_selected_source"),
            "enabled":bool(cfg.get("enabled",False)),
            "executeGit":bool(cfg.get("execute_git",False)),
            "baseBranch":base_branch,
            "workBranch":work_branch,
            "pushBranch":push_branch,
            "pushRequested":bool(cfg.get("push",False)),
            "branchSyncStrategy":"prefer_origin_work_branch_else_base_branch",
            "gitBinaryAvailable":False,
            "gitVersion":"",
            "gitExecuted":False,
            "committed":False,
            "pushed":False,
            "prRequested":bool(pr_cfg.get("enabled",False)),
            "prNetworkEnabled":bool(pr_cfg.get("execute_network_calls",False)),
            "prCreated":False
        }

        git_check=self.git_preflight()
        report.update(git_check)
        self.ctx.write_json("git/preflight_report.json",git_check)

        if not cfg.get("enabled",False):
            report["reason"]="git_finalization_disabled"
            self.finish(report)
            return AgentResult(self.name,"success",0.9,report,report)
        if not cfg.get("execute_git",False):
            report["reason"]="execute_git_false"
            self.finish(report)
            return AgentResult(self.name,"success",0.85,report,report)
        if not git_check.get("gitBinaryAvailable"):
            report["reason"]="git_binary_missing"
            self.finish(report)
            return AgentResult(self.name,"failed_open",0.25,report,report)

        repo_url=cfg.get("repo_url","")
        token=os.environ.get(cfg.get("token_env","GIT_TOKEN"),"")
        username=os.environ.get(cfg.get("username_env","GIT_USERNAME"),"")

        if not repo_url:
            report["reason"]="repo_url_missing"
            self.finish(report)
            return AgentResult(self.name,"failed_open",0.25,report,report)
        if not token:
            report["reason"]="git_token_missing"
            self.finish(report)
            return AgentResult(self.name,"failed_open",0.25,report,report)

        clone_dir=Path(cfg.get("clone_dir","/workspace/final-repo"))
        auth_url=self.github_https_token_url(repo_url,token,username)
        report["authMode"]="https_token_url_redacted"
        report["repoUrl"]=self.redact(auth_url,token)
        env=self.git_env()

        try:
            if clone_dir.exists():
                shutil.rmtree(clone_dir)

            clone=self.run_cmd(["git","clone",auth_url,str(clone_dir)],timeout=600,redact_token=token,env=env,check=False)
            if clone["returncode"]!=0:
                report.update({
                    "reason":"git_clone_failed",
                    "cloneReturnCode":clone["returncode"],
                    "cloneStdout":clone.get("stdout","")[-2000:],
                    "cloneStderr":clone.get("stderr","")[-4000:],
                    "likelyCause":self.likely_git_cause(clone.get("stderr","")+clone.get("stdout",""))
                })
                self.finish(report)
                return AgentResult(self.name,"failed_open",0.35,report,report)

            report["gitExecuted"]=True

            self.run_cmd(["git","fetch","origin","--prune"],cwd=clone_dir,check=False,timeout=180,redact_token=token,env=env)

            # New behavior:
            # If origin/develop exists, base local develop from origin/develop.
            # Else create develop from origin/main/main.
            remote_work=self.run_cmd(["git","rev-parse","--verify",f"origin/{work_branch}"],cwd=clone_dir,check=False,timeout=30,redact_token=token,env=env)
            if remote_work.get("returncode")==0:
                self.run_cmd(["git","checkout","-B",work_branch,f"origin/{work_branch}"],cwd=clone_dir,timeout=120,redact_token=token,env=env)
                report["workBranchBase"]=f"origin/{work_branch}"
            else:
                checkout_base=self.run_cmd(["git","checkout",base_branch],cwd=clone_dir,check=False,timeout=120,redact_token=token,env=env)
                if checkout_base.get("returncode") != 0:
                    self.run_cmd(["git","checkout","-B",base_branch,f"origin/{base_branch}"],cwd=clone_dir,check=False,timeout=120,redact_token=token,env=env)
                self.run_cmd(["git","checkout","-B",work_branch],cwd=clone_dir,timeout=120,redact_token=token,env=env)
                report["workBranchBase"]=base_branch

            copied=[]
            for rel in cfg.get("copy_artifacts_to",["generated/","final/","summary/","quality/","analysis/","codegen/","docs/","self_healing/"]):
                src=self.ctx.output/rel
                if src.exists():
                    dst=clone_dir/"qaira-generated"/rel
                    if src.is_dir():
                        if dst.exists():
                            shutil.rmtree(dst)
                        shutil.copytree(src,dst)
                    else:
                        dst.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(src,dst)
                    copied.append(rel)

            self.run_cmd(["git","add","qaira-generated"],cwd=clone_dir,timeout=120,redact_token=token,env=env)
            status=self.run_cmd(["git","status","--porcelain"],cwd=clone_dir,timeout=120,redact_token=token,check=False,env=env)
            report["copied"]=copied

            if not status.get("stdout","").strip():
                report["reason"]="no_changes_to_commit"
            else:
                self.run_cmd(["git","config","user.email","qaira-agent@example.local"],cwd=clone_dir,timeout=30,redact_token=token,env=env)
                self.run_cmd(["git","config","user.name","QAira Agent"],cwd=clone_dir,timeout=30,redact_token=token,env=env)
                self.run_cmd(["git","commit","-m",cfg.get("commit_message","chore: update generated QAira artifacts")],cwd=clone_dir,timeout=120,redact_token=token,env=env)
                report["committed"]=True

                if cfg.get("push",False):
                    # Normal push now works because branch starts from origin/develop when it exists.
                    push=self.run_cmd(["git","push","-u",auth_url,f"{work_branch}:{push_branch}"],cwd=clone_dir,check=False,timeout=300,redact_token=token,env=env)
                    if push["returncode"]==0:
                        report["pushed"]=True
                        if pr_cfg.get("enabled",False):
                            pr=self.create_pr(repo_url,token,push_branch,branch_cfg.get("pr_base_branch") or pr_cfg.get("base_branch") or base_branch,pr_cfg)
                            report["pullRequest"]=pr
                            report["prCreated"]=bool(pr.get("created"))
                    else:
                        report.update({
                            "reason":"git_push_failed",
                            "pushReturnCode":push["returncode"],
                            "pushStdout":push.get("stdout","")[-2000:],
                            "pushStderr":push.get("stderr","")[-4000:],
                            "likelyCause":self.likely_git_cause(push.get("stderr","")+push.get("stdout",""))
                        })
                else:
                    report["reason"]="committed_locally_push_false"

        except Exception as e:
            report.update({"error":str(e),"failedOpen":True})

        self.finish(report)
        return AgentResult(
            self.name,
            "success" if not report.get("error") and report.get("reason") not in {"git_push_failed","git_clone_failed"} else "failed_open",
            0.95 if report.get("pushed") else 0.9 if report.get("committed") or report.get("reason") in {"no_changes_to_commit","execute_git_false","committed_locally_push_false"} else 0.4,
            report,
            report
        )

    def github_https_token_url(self,repo_url,token,username=""):
        if not repo_url.startswith("https://"):
            return repo_url
        user=quote(username or "x-access-token",safe="")
        tok=quote(token,safe="")
        return repo_url.replace("https://",f"https://{user}:{tok}@")

    def git_env(self):
        env=os.environ.copy()
        env["GIT_TERMINAL_PROMPT"]="0"
        return env

    def run_cmd(self,cmd,cwd=None,timeout=120,check=True,redact_token="",env=None):
        safe_cmd=[self.redact(c,redact_token) for c in cmd]
        item={"cmd":safe_cmd,"cwd":str(cwd) if cwd else None}
        try:
            p=subprocess.run(cmd,cwd=cwd,timeout=timeout,capture_output=True,text=True,env=env)
            item.update({"returncode":p.returncode,"stdout":self.redact(p.stdout,redact_token),"stderr":self.redact(p.stderr,redact_token)})
            self.commands.append(item)
            self.ctx.write_json("git/command_log.json",{"commands":self.commands})
            if check and p.returncode!=0:
                raise RuntimeError(f"command failed: {safe_cmd} rc={p.returncode} stderr={item['stderr'][-1000:]}")
            return item
        except Exception as e:
            item.update({"exception":str(e)})
            self.commands.append(item)
            self.ctx.write_json("git/command_log.json",{"commands":self.commands})
            if check:
                raise
            return item

    def redact(self,text,token):
        if text is None:
            return ""
        text=str(text)
        if token:
            text=text.replace(token,"<redacted>").replace(quote(token,safe=""),"<redacted>")
        return text

    def git_preflight(self):
        try:
            p=subprocess.run(["git","--version"],capture_output=True,text=True,timeout=10)
            return {"gitBinaryAvailable":p.returncode==0,"gitVersion":p.stdout.strip(),"gitVersionStderr":p.stderr.strip()}
        except Exception as e:
            return {"gitBinaryAvailable":False,"gitVersion":"","gitError":str(e)}

    def likely_git_cause(self,text):
        t=(text or "").lower()
        if "authentication failed" in t or "could not read username" in t or "terminal prompts disabled" in t:
            return "authentication_failed_token_missing_invalid_or_not_accepted"
        if "permission" in t or "403" in t or "write access" in t:
            return "token_lacks_repo_write_permission"
        if "protected branch" in t or "gh006" in t:
            return "branch_protection_rejected_push"
        if "repository not found" in t:
            return "repo_not_found_or_token_no_access"
        if "non-fast-forward" in t:
            return "non_fast_forward_rejected_remote_branch_changed"
        if "src refspec" in t:
            return "branch_refspec_issue"
        return "inspect_git_command_log"

    def create_pr(self,repo_url,token,head,base_branch,pr_cfg):
        if not pr_cfg.get("execute_network_calls",False):
            return {"created":False,"reason":"pr_execute_network_calls_false"}
        m=re.search(r"github\.com[:/](.+?)/(.+?)(?:\.git)?$",repo_url)
        if not m:
            return {"created":False,"reason":"unsupported_repo_url"}
        owner,repo=m.group(1),m.group(2).replace(".git","")
        url=f"https://api.github.com/repos/{owner}/{repo}/pulls"
        body_text=pr_cfg.get("body","Automated QAira semantic compiler update.")
        body_file=pr_cfg.get("body_file")
        if body_file and Path(body_file).exists():
            try:
                body_text=Path(body_file).read_text(encoding="utf-8")
            except Exception:
                pass
        body=json.dumps({
            "title":pr_cfg.get("title","QAira generated API contracts and tests"),
            "body":body_text,
            "head":head,
            "base":base_branch
        }).encode()
        req=urllib.request.Request(url,data=body,headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/vnd.github+json",
            "Content-Type":"application/json"
        })
        try:
            with urllib.request.urlopen(req,timeout=30) as resp:
                data=json.loads(resp.read().decode())
            return {"created":True,"url":data.get("html_url"),"number":data.get("number")}
        except Exception as e:
            return {"created":False,"reason":"pr_api_failed","error":str(e)}

    def finish(self,report):
        self.ctx.write_json("git/finalization_report.json",report)
        self.ctx.write_json("git/command_log.json",{"commands":self.commands})
