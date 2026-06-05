from __future__ import annotations
import json, os, time, urllib.request, re

class LLMClient:
    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger
        # Compatibility: prefer llm_review but fall back to llm.
        self.cfg=(ctx.config.get("llm_review") or ctx.config.get("llm") or {})

    def review(self, name, payload, default=None):
        default=default or {"accepted":True,"suggestions":[],"reason":"llm_fail_open_default"}
        enabled=bool(self.cfg.get("enabled",False))
        execute=bool(self.cfg.get("execute_network_calls",False))
        max_chars=int(self.cfg.get("max_prompt_chars",12000))

        # Never embed raw Python repr or unescaped text. JSON is the transport.
        prompt={
            "instruction": (
                "Review the agent/run result. Rank issues. Suggest deterministic remediation actions only. "
                "Return valid JSON only with keys: accepted:boolean, suggestions:array, reason:string."
            ),
            "name":name,
            "payload":payload
        }
        prompt_json=safe_json_dumps(prompt)[:max_chars]
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
                body=safe_json_dumps({
                    "model":model,
                    "temperature":0,
                    "response_format":{"type":"json_object"},
                    "messages":[
                        {"role":"system","content":"You are a deterministic QA architecture reviewer. Return valid JSON only."},
                        {"role":"user","content":prompt_json}
                    ]
                }).encode("utf-8")

                req=urllib.request.Request(endpoint,data=body,headers={
                    "Content-Type":"application/json",
                    "Authorization":"Bearer "+api_key
                })
                with urllib.request.urlopen(req,timeout=timeout) as resp:
                    data=json.loads(resp.read().decode("utf-8", errors="replace"))

                content=data.get("choices",[{}])[0].get("message",{}).get("content","")
                self.ctx.write_text(f"llm/raw/{safe_name(name)}.txt", content)

                parsed=parse_llm_json(content)
                parsed["networkCallExecuted"]=True
                parsed["parseSafe"]=True
                self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",parsed)
                return parsed
            except Exception as e:
                self.logger.log("LLM-ERROR",name,str(e),attempt=attempt)
                time.sleep(1)

        result={**default,"llmEnabled":True,"networkCallExecuted":False,"error":"llm_failed_after_retries","failOpen":True}
        self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",result)
        return result

def safe_json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)

def parse_llm_json(text):
    if not text:
        return {"accepted":True,"suggestions":[],"reason":"empty_llm_text_fail_open"}
    try:
        data=json.loads(text)
        return normalize_llm_result(data)
    except Exception:
        pass

    # ReAct or markdown accidental wrappers: extract first JSON object safely.
    cleaned=text.strip()
    cleaned=re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned=re.sub(r"```$", "", cleaned).strip()

    start=cleaned.find("{")
    end=cleaned.rfind("}")
    if start>=0 and end>start:
        fragment=cleaned[start:end+1]
        try:
            return normalize_llm_result(json.loads(fragment))
        except Exception as e:
            return {
                "accepted":True,
                "suggestions":[],
                "reason":"malformed_json_fail_open",
                "parseError":str(e),
                "rawPreview":cleaned[:1000]
            }

    return {"accepted":True,"suggestions":[],"reason":"no_json_found_fail_open","rawPreview":cleaned[:1000]}

def normalize_llm_result(data):
    if not isinstance(data,dict):
        return {"accepted":True,"suggestions":[],"reason":"non_object_llm_result_fail_open","raw":data}
    if "suggestions" not in data:
        data["suggestions"]=[]
    if "accepted" not in data:
        data["accepted"]=True
    if "reason" not in data:
        data["reason"]="llm_review_completed"
    return data

def safe_name(s):
    return re.sub(r"[^a-zA-Z0-9_.-]+","_",str(s))[:120]
