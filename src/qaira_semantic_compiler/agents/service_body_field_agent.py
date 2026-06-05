from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.jsparse import balanced_block, split_top_level_args, object_keys
import re

BAD_FIELDS={
    "length","equals","map","filter","find","some","every","then","catch","finally",
    "json","send","status","headers","query","params","body","user","req","res","reply",
    "request","response","id"
}

class ServiceBodyFieldAgent:
    name="ServiceBodyFieldAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        idx=self.ctx.state["index"]
        patterns=[]
        by_route={}

        for edge in self.ctx.state.get("serviceEdges",[]):
            route_id=edge.get("from")
            service_file=edge.get("toFile")
            method=edge.get("method")
            if not service_file or not method:
                continue

            try:
                text=idx.read(service_file)
            except Exception:
                continue

            method_info=self.extract_method(text, method)
            block=method_info.get("block","")
            params=method_info.get("params",[])
            if not block:
                continue

            # Which service parameters are likely body args?
            body_param_names=set()
            for i,arg in enumerate(edge.get("args",[])):
                arg_l=arg.lower()
                if "body" in arg_l or "payload" in arg_l or "dto" in arg_l or "data" in arg_l or "input" in arg_l:
                    if i < len(params):
                        body_param_names.add(params[i])
                # if object literal passed directly to service, extract its keys
                if arg.strip().startswith("{"):
                    fs=object_keys(arg.strip().strip("{}"))
                    self.add(route_id, service_file, method, fs, patterns, by_route, 0.82, "route_service_call_object_literal")

            if not body_param_names:
                body_param_names |= {p for p in params if p.lower() in {"body","payload","data","input","dto","requestbody"}}

            fields=set()

            for p in body_param_names:
                fields |= self.extract_fields_for_alias(block,p)

            # Also inspect common aliases inside service.
            for alias in ["body","payload","data","input","dto","requestBody"]:
                fields |= self.extract_fields_for_alias(block,alias)

            # Object literal DB/repository writes inside this method.
            fields |= self.extract_write_object_fields(block)

            fields=self.clean(fields)
            if fields:
                self.add(route_id, service_file, method, fields, patterns, by_route, 0.84, "service_method_body_usage")

        self.ctx.state["serviceBodyFieldsByRoute"]={k:sorted(v) for k,v in by_route.items()}
        self.ctx.write_json("patterns/service_body_field_patterns.json",{
            "count":len(patterns),
            "routes":len(by_route),
            "items":patterns
        })
        return AgentResult(self.name,"success" if patterns else "failed_open",0.85 if patterns else 0.25,{"patterns":len(patterns),"routes":len(by_route)},{})

    def add(self,route_id,service_file,method,fields,patterns,by_route,confidence,source):
        fields=self.clean(fields)
        if not fields: return
        patterns.append({"routeId":route_id,"serviceFile":service_file,"method":method,"fields":sorted(fields),"confidence":confidence,"source":source})
        by_route.setdefault(route_id,set()).update(fields)

    def clean(self,fields):
        out=set()
        for f in fields:
            if not f or f in BAD_FIELDS: continue
            if f.startswith("_"): continue
            if len(f)>60: continue
            out.add(f)
        return out

    def extract_method(self,text,method):
        pats=[
            r"(?:async\s+)?"+re.escape(method)+r"\s*\(([^)]*)\)\s*\{",
            r"(?:const|let|var)\s+"+re.escape(method)+r"\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
            re.escape(method)+r"\s*:\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
            r"exports\."+re.escape(method)+r"\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
            r"module\.exports\."+re.escape(method)+r"\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
        ]
        for pat in pats:
            m=re.search(pat,text)
            if not m: continue
            params=[p.strip().split("=")[0].strip() for p in split_top_level_args(m.group(1)) if p.strip()]
            start=text.find("{",m.end()-1)
            return {"params":params,"block":balanced_block(text,start)}
        return {"params":[],"block":""}

    def extract_fields_for_alias(self,block,alias):
        fields=set()
        fields |= set(re.findall(r"\b"+re.escape(alias)+r"\.([A-Za-z_$][\w$]*)",block))
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*"+re.escape(alias),block):
            for part in split_top_level_args(m.group(1)):
                name=part.strip().split(":")[0].strip()
                if re.match(r"^[A-Za-z_$][\w$]*$",name):
                    fields.add(name)
        return fields

    def extract_write_object_fields(self,block):
        fields=set()
        # Prisma/ORM data object
        for m in re.finditer(r"\bdata\s*:\s*\{([\s\S]{0,2500}?)\}",block):
            fields |= object_keys(m.group(1))
        # insert/update/create/save object
        for m in re.finditer(r"\.(?:insert|update|create|save|upsert)\s*\(\s*\{([\s\S]{0,2500}?)\}\s*\)",block):
            fields |= object_keys(m.group(1))
        return fields
