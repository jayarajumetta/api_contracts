from qaira_semantic_compiler.core.context import AgentResult
from pathlib import Path
import os, shutil, subprocess, datetime, json, urllib.request, re

class GitFinalizationAgent:
    name="GitFinalizationAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger
        self.commands=[]

    def run(self):
        cfg=self.ctx.config.get("git_finalization") or self.ctx.config.get("git_push") or self.ctx.config.get("git") or {}
        pr_cfg=self.ctx.config.get("pull_request") or {}
        report={
            "enabled":bool(cfg.get("enabled",False)),
            "executeGit":bool(cfg.get("execute_git",False)),
            "pushRequested":bool(cfg.get("push",False)),
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
        base_branch=cfg.get("target_branch","develop")
        work_branch=base_branch
        if cfg.get("create_branch", True):
            suffix=datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
            work_branch=f"{cfg.get('branch_prefix',cfg.get('create_branch_prefix','qaira-agent'))}-{suffix}"

        try:
            if clone_dir.exists():
                shutil.rmtree(clone_dir)

            # Safer auth: do not embed token in URL. Use extraHeader.
            # This avoids malformed URLs when tokens contain special characters.
            auth_header=f"Authorization: Bearer {token}"
            self.run_cmd(["git","-c",f"http.extraHeader={auth_header}","clone",repo_url,str(clone_dir)], timeout=600, redact_token=token)
            report["gitExecuted"]=True

            # Checkout target branch. If missing locally, try origin/base_branch.
            checkout=self.run_cmd(["git","checkout",base_branch],cwd=clone_dir,check=False,timeout=120, redact_token=token)
            if checkout["returncode"] != 0:
                self.run_cmd(["git","checkout","-B",base_branch,f"origin/{base_branch}"],cwd=clone_dir,check=False,timeout=120, redact_token=token)

            if work_branch != base_branch:
                self.run_cmd(["git","checkout","-B",work_branch],cwd=clone_dir,timeout=120, redact_token=token)

            copied=[]
            for rel in cfg.get("copy_artifacts_to",["generated/","final/","summary/","quality/","analysis/"]):
                src=self.ctx.output/rel
                if src.exists():
                    dst=clone_dir/"qaira-generated"/rel
                    if src.is_dir():
                        if dst.exists(): shutil.rmtree(dst)
                        shutil.copytree(src,dst)
                    else:
                        dst.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(src,dst)
                    copied.append(rel)

            self.run_cmd(["git","add","qaira-generated"],cwd=clone_dir,timeout=120, redact_token=token)
            status=self.run_cmd(["git","status","--porcelain"],cwd=clone_dir,timeout=120, redact_token=token, check=False)
            report["copied"]=copied
            report["branch"]=work_branch

            if not status.get("stdout","").strip():
                report["reason"]="no_changes_to_commit"
            else:
                self.run_cmd(["git","config","user.email","qaira-agent@example.local"],cwd=clone_dir,timeout=30, redact_token=token)
                self.run_cmd(["git","config","user.name","QAira Agent"],cwd=clone_dir,timeout=30, redact_token=token)
                self.run_cmd(["git","commit","-m",cfg.get("commit_message","chore: update generated QAira artifacts")],cwd=clone_dir,timeout=120, redact_token=token)
                report["committed"]=True

                if cfg.get("push",False):
                    push_cmd=["git","-c",f"http.extraHeader={auth_header}","push","-u","origin",work_branch]
                    push=self.run_cmd(push_cmd,cwd=clone_dir,check=False,timeout=300,redact_token=token)
                    if push["returncode"] == 0:
                        report["pushed"]=True
                        if pr_cfg.get("enabled",False):
                            pr=self.create_pr(repo_url,token,work_branch,base_branch,pr_cfg)
                            report["pullRequest"]=pr
                            report["prCreated"]=bool(pr.get("created"))
                    else:
                        report["reason"]="git_push_failed"
                        report["pushReturnCode"]=push["returncode"]
                        report["pushStdout"]=push.get("stdout","")[-2000:]
                        report["pushStderr"]=push.get("stderr","")[-4000:]
                        report["likelyCause"]=self.likely_push_cause(push.get("stderr","")+push.get("stdout",""))
                else:
                    report["reason"]="committed_locally_push_false"

        except Exception as e:
            report.update({"error":str(e),"failedOpen":True})

        self.finish(report)
        return AgentResult(
            self.name,
            "success" if not report.get("error") and report.get("reason") not in {"git_push_failed"} else "failed_open",
            0.9 if report.get("pushed") or report.get("committed") or report.get("reason") in {"no_changes_to_commit","execute_git_false","committed_locally_push_false"} else 0.4,
            report,
            report
        )

    def run_cmd(self,cmd,cwd=None,timeout=120,check=True,redact_token=""):
        safe_cmd=[c.replace(redact_token,"<redacted>") if redact_token else c for c in cmd]
        item={"cmd":safe_cmd,"cwd":str(cwd) if cwd else None}
        try:
            p=subprocess.run(cmd,cwd=cwd,timeout=timeout,capture_output=True,text=True)
            item.update({
                "returncode":p.returncode,
                "stdout":self.redact(p.stdout,redact_token),
                "stderr":self.redact(p.stderr,redact_token)
            })
            self.commands.append(item)
            self.ctx.write_json("git/command_log.json",{"commands":self.commands})
            if check and p.returncode != 0:
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
        if not text: return ""
        if token:
            text=text.replace(token,"<redacted>")
        return text

    def git_preflight(self):
        try:
            p=subprocess.run(["git","--version"],capture_output=True,text=True,timeout=10)
            return {"gitBinaryAvailable":p.returncode==0,"gitVersion":p.stdout.strip(),"gitVersionStderr":p.stderr.strip()}
        except Exception as e:
            return {"gitBinaryAvailable":False,"gitVersion":"","gitError":str(e)}

    def likely_push_cause(self,text):
        t=(text or "").lower()
        if "authentication failed" in t or "could not read username" in t:
            return "authentication_failed_or_token_not_accepted"
        if "permission" in t or "403" in t or "write access" in t:
            return "token_lacks_repo_write_permission"
        if "protected branch" in t or "gh006" in t:
            return "branch_protection_rejected_push"
        if "repository not found" in t:
            return "repo_not_found_or_token_no_access"
        if "src refspec" in t:
            return "branch_refspec_issue"
        if "non-fast-forward" in t:
            return "non_fast_forward_rejected"
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
            "base":pr_cfg.get("base_branch",base_branch)
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
