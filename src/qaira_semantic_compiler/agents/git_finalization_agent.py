from qaira_semantic_compiler.core.context import AgentResult
from pathlib import Path
import os, shutil, subprocess, datetime, json, urllib.request, re

class GitFinalizationAgent:
    name="GitFinalizationAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

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
            self.ctx.write_json("git/finalization_report.json",report)
            return AgentResult(self.name,"success",0.9,report,report)

        if not cfg.get("execute_git",False):
            report["reason"]="execute_git_false"
            self.ctx.write_json("git/finalization_report.json",report)
            return AgentResult(self.name,"success",0.85,report,report)

        if not git_check.get("gitBinaryAvailable"):
            report["reason"]="git_binary_missing"
            self.ctx.write_json("git/finalization_report.json",report)
            return AgentResult(self.name,"failed_open",0.25,report,report)

        repo_url=cfg.get("repo_url","")
        token=os.environ.get(cfg.get("token_env","GIT_TOKEN"),"")
        username=os.environ.get(cfg.get("username_env","GIT_USERNAME"),"")

        if not repo_url:
            report["reason"]="repo_url_missing"
            self.ctx.write_json("git/finalization_report.json",report)
            return AgentResult(self.name,"failed_open",0.25,report,report)
        if not token:
            report["reason"]="git_token_missing"
            self.ctx.write_json("git/finalization_report.json",report)
            return AgentResult(self.name,"failed_open",0.25,report,report)

        clone_dir=Path(cfg.get("clone_dir","/workspace/final-repo"))
        base_branch=cfg.get("target_branch","develop")
        work_branch=base_branch
        if cfg.get("create_branch",True):
            suffix=datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
            work_branch=f"{cfg.get('branch_prefix','qaira-agent')}-{suffix}"

        try:
            if clone_dir.exists():
                shutil.rmtree(clone_dir)

            auth_url=self.auth_url(repo_url,username,token)
            subprocess.run(["git","clone",auth_url,str(clone_dir)],check=True,timeout=600)
            report["gitExecuted"]=True

            subprocess.run(["git","checkout",base_branch],cwd=clone_dir,check=False,timeout=120)
            if work_branch!=base_branch:
                subprocess.run(["git","checkout","-b",work_branch],cwd=clone_dir,check=True,timeout=120)

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

            subprocess.run(["git","add","qaira-generated"],cwd=clone_dir,check=True,timeout=120)
            status=subprocess.check_output(["git","status","--porcelain"],cwd=clone_dir,timeout=120).decode()
            report["copied"]=copied
            report["branch"]=work_branch

            if not status.strip():
                report["reason"]="no_changes_to_commit"
            else:
                subprocess.run(["git","config","user.email","qaira-agent@example.local"],cwd=clone_dir,check=True)
                subprocess.run(["git","config","user.name","QAira Agent"],cwd=clone_dir,check=True)
                subprocess.run(["git","commit","-m",cfg.get("commit_message","chore: update generated QAira artifacts")],cwd=clone_dir,check=True,timeout=120)
                report["committed"]=True

                if cfg.get("push",False):
                    subprocess.run(["git","push","origin",work_branch],cwd=clone_dir,check=True,timeout=300)
                    report["pushed"]=True

                    if pr_cfg.get("enabled",False):
                        pr=self.create_pr(repo_url,token,work_branch,base_branch,pr_cfg)
                        report["pullRequest"]=pr
                        report["prCreated"]=bool(pr.get("created"))
                else:
                    report["reason"]="committed_locally_push_false"

        except Exception as e:
            report.update({"error":str(e),"failedOpen":True})

        self.ctx.write_json("git/finalization_report.json",report)
        return AgentResult(
            self.name,
            "success" if not report.get("error") else "failed_open",
            0.9 if report.get("committed") or report.get("reason") in {"no_changes_to_commit","execute_git_false","committed_locally_push_false"} else 0.4,
            report,
            report
        )

    def git_preflight(self):
        try:
            out=subprocess.check_output(["git","--version"],timeout=10).decode().strip()
            return {"gitBinaryAvailable":True,"gitVersion":out}
        except Exception as e:
            return {"gitBinaryAvailable":False,"gitVersion":"","gitError":str(e)}

    def auth_url(self,repo_url,username,token):
        if repo_url.startswith("https://"):
            if username:
                return repo_url.replace("https://",f"https://{username}:{token}@")
            return repo_url.replace("https://",f"https://x-access-token:{token}@")
        return repo_url

    def create_pr(self,repo_url,token,head,base_branch,pr_cfg):
        if not pr_cfg.get("execute_network_calls",False):
            return {"created":False,"reason":"pr_execute_network_calls_false"}
        m=re.search(r"github\.com[:/](.+?)/(.+?)(?:\.git)?$",repo_url)
        if not m:
            return {"created":False,"reason":"unsupported_repo_url"}
        owner,repo=m.group(1),m.group(2).replace(".git","")
        url=f"https://api.github.com/repos/{owner}/{repo}/pulls"
        body=json.dumps({
            "title":pr_cfg.get("title","QAira generated API contracts and tests"),
            "body":pr_cfg.get("body","Automated QAira semantic compiler update."),
            "head":head,
            "base":pr_cfg.get("base_branch",base_branch)
        }).encode()
        req=urllib.request.Request(url,data=body,headers={
            "Authorization":"Bearer "+token,
            "Accept":"application/vnd.github+json",
            "Content-Type":"application/json"
        })
        with urllib.request.urlopen(req,timeout=30) as resp:
            data=json.loads(resp.read().decode())
        return {"created":True,"url":data.get("html_url"),"number":data.get("number")}
