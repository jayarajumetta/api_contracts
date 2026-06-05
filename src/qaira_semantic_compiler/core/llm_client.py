from __future__ import annotations
import json, os, time, urllib.request, re

class LLMClient:
    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger
        self.cfg=(ctx.config.get("llm_review") or ctx.config.get("llm") or {})
        self.counter_path=ctx.output/"llm"/"call_count.json"

    def can_call(self):
        max_calls=int(self.cfg.get("calls_per_run", self.cfg.get("max_calls_per_run", 1)))
        count=0
        if self.counter_path.exists():
            try: count=json.loads(self.counter_path.read_text()).get("count",0)
            except Exception: count=0
        return count < max_calls, count, max_calls

    def inc_call(self):
        count=0
        if self.counter_path.exists():
            try: count=json.loads(self.counter_path.read_text()).get("count",0)
            except Exception: count=0
        self.counter_path.parent.mkdir(parents=True,exist_ok=True)
        self.counter_path.write_text(json.dumps({"count":count+1}),encoding="utf-8")

    def review(self, name, payload, default=None):
        default=default or {"accepted":True,"suggestions":[],"reason":"llm_fail_open_default"}
        enabled=bool(self.cfg.get("enabled",False))
        execute=bool(self.cfg.get("execute_network_calls",False))
        max_chars=int(self.cfg.get("max_prompt_chars",12000))
        ok,count,max_calls=self.can_call()

        prompt={
            "instruction": (
                "You are reviewing ONE compact iteration_context for an API contract discovery agent. "
                "Do not ask for logs. Rank root cause issues. Suggest only deterministic remediations mapped to a specific agent file. "
                "Return JSON keys: accepted, score, issues, suggestedAgentDeltas. "
                "suggestedAgentDeltas items must include agentName, reason, changeType, patchIntent, confidence."
            ),
            "name":name,
            "payload":payload
        }
        prompt_json=safe_json_dumps(prompt)[:max_chars]
        self.ctx.write_json(f"llm/prompts/{safe_name(name)}.json",prompt)

        if not enabled or not execute:
            result={**default,"llmEnabled":enabled,"networkCallExecuted":False,"note":"LLM prompt saved; fail-open deterministic flow continued","callCount":count,"maxCalls":max_calls}
            self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",result)
            return result

        if not ok:
            result={**default,"llmEnabled":True,"networkCallExecuted":False,"reason":"llm_call_budget_exhausted","callCount":count,"maxCalls":max_calls}
            self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",result)
            return result

        api_key=os.environ.get(self.cfg.get("api_key_env","OPENAI_API_KEY"),"")
        if not api_key:
            result={**default,"llmEnabled":True,"networkCallExecuted":False,"error":"missing_api_key"}
            self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",result)
            return result

        endpoint=self.cfg.get("endpoint","https://api.openai.com/v1/chat/completions")
        model=self.cfg.get("model","gpt-4.1-mini")
        retries=int(self.cfg.get("max_retries",0))
        timeout=int(self.cfg.get("timeout_seconds",20))

        for attempt in range(retries+1):
            try:
                body=safe_json_dumps({
                    "model":model,
                    "temperature":0,
                    "response_format":{"type":"json_object"},
                    "messages":[
                        {"role":"system","content":"Return valid JSON only. No markdown. No chain of thought."},
                        {"role":"user","content":prompt_json}
                    ]
                }).encode("utf-8")
                req=urllib.request.Request(endpoint,data=body,headers={
                    "Content-Type":"application/json",
                    "Authorization":"Bearer "+api_key
                })
                with urllib.request.urlopen(req,timeout=timeout) as resp:
                    data=json.loads(resp.read().decode("utf-8",errors="replace"))
                self.inc_call()
                content=data.get("choices",[{}])[0].get("message",{}).get("content","")
                self.ctx.write_text(f"llm/raw/{safe_name(name)}.txt",content)
                parsed=parse_llm_json(content)
                parsed["networkCallExecuted"]=True
                parsed["parseSafe"]=True
                self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",parsed)
                return parsed
            except Exception as e:
                # On 429, do not retry aggressively. Save and fail open.
                self.logger.log("LLM-ERROR",name,str(e),attempt=attempt)
                if "429" in str(e):
                    break
                time.sleep(1)

        result={**default,"llmEnabled":True,"networkCallExecuted":False,"error":"llm_failed_or_rate_limited","failOpen":True}
        self.ctx.write_json(f"llm/responses/{safe_name(name)}.json",result)
        return result

def safe_json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)

def parse_llm_json(text):
    if not text:
        return {"accepted":True,"suggestedAgentDeltas":[],"reason":"empty_llm_text_fail_open"}
    try:
        data=json.loads(text)
        return normalize(data)
    except Exception:
        cleaned=text.strip()
        cleaned=re.sub(r"^```(?:json)?","",cleaned,flags=re.I).strip()
        cleaned=re.sub(r"```$","",cleaned).strip()
        start=cleaned.find("{"); end=cleaned.rfind("}")
        if start>=0 and end>start:
            try: return normalize(json.loads(cleaned[start:end+1]))
            except Exception as e:
                return {"accepted":True,"suggestedAgentDeltas":[],"reason":"malformed_json_fail_open","parseError":str(e),"rawPreview":cleaned[:1000]}
    return {"accepted":True,"suggestedAgentDeltas":[],"reason":"no_json_found_fail_open","rawPreview":text[:1000]}

def normalize(data):
    if not isinstance(data,dict):
        return {"accepted":True,"suggestedAgentDeltas":[],"reason":"non_object_fail_open","raw":data}
    data.setdefault("accepted",True)
    data.setdefault("suggestedAgentDeltas", data.get("suggestions", []))
    data.setdefault("reason","llm_review_completed")
    return data

def safe_name(s):
    return re.sub(r"[^a-zA-Z0-9_.-]+","_",str(s))[:120]
