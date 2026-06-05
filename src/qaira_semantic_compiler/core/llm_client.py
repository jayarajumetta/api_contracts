from __future__ import annotations
import json, os, time, urllib.request

class LLMClient:
    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger
        self.cfg=(ctx.config.get("llm_review") or ctx.config.get("llm") or {})

    def review(self, name, payload, default=None):
        default=default or {"accepted":True,"suggestions":[],"reason":"llm_fail_open_default"}
        enabled=bool(self.cfg.get("enabled",False))
        execute=bool(self.cfg.get("execute_network_calls",False))
        max_chars=int(self.cfg.get("max_prompt_chars",12000))
        prompt={
            "instruction":"Review the agent/run result. Rank issues. Suggest deterministic remediation actions only. Return JSON.",
            "name":name,
            "payload":payload
        }
        raw=json.dumps(prompt,default=str)[:max_chars]
        self.ctx.write_json(f"llm/prompts/{safe_name(name)}.json",prompt)

        if not enabled or not execute:
            result={**default,"llmEnabled":enabled,"networkCallExecuted":False,"note":"LLM prompt saved; fail-open deterministic flow continued"}
            self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",result)
            return result

        api_key=os.environ.get(self.cfg.get("api_key_env","OPENAI_API_KEY"),"")
        if not api_key:
            result={**default,"llmEnabled":True,"networkCallExecuted":False,"error":"missing_api_key"}
            self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",result)
            return result

        endpoint=self.cfg.get("endpoint","https://api.openai.com/v1/chat/completions")
        model=self.cfg.get("model","gpt-4.1-mini")
        retries=int(self.cfg.get("max_retries",1))
        timeout=int(self.cfg.get("timeout_seconds",20))

        for attempt in range(retries+1):
            try:
                body=json.dumps({
                    "model":model,
                    "temperature":0,
                    "messages":[
                        {"role":"system","content":"You are a deterministic QA architecture reviewer. Return JSON only."},
                        {"role":"user","content":raw}
                    ]
                }).encode("utf-8")
                req=urllib.request.Request(endpoint,data=body,headers={
                    "Content-Type":"application/json",
                    "Authorization":"Bearer "+api_key
                })
                with urllib.request.urlopen(req,timeout=timeout) as resp:
                    data=json.loads(resp.read().decode("utf-8"))
                content=data["choices"][0]["message"]["content"]
                try:
                    parsed=json.loads(content)
                except Exception:
                    parsed={"accepted":True,"suggestions":[],"raw":content}
                parsed["networkCallExecuted"]=True
                self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",parsed)
                return parsed
            except Exception as e:
                self.logger.log("LLM-ERROR",name,str(e),attempt=attempt)
                time.sleep(1)
        result={**default,"llmEnabled":True,"networkCallExecuted":False,"error":"llm_failed_after_retries"}
        self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",result)
        return result

def safe_name(s):
    import re
    return re.sub(r"[^a-zA-Z0-9_.-]+","_",str(s))[:120]
