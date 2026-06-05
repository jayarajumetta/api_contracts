from __future__ import annotations

import argparse, json, os, re, hashlib, time
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

try:
    import yaml
except Exception:
    yaml = None

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript as tsjavascript
    import tree_sitter_typescript as tstypescript
    TREE_SITTER_AVAILABLE = True
except Exception:
    TREE_SITTER_AVAILABLE = False
    Language = None
    Parser = None

EXCLUDED_DIRS={".git","node_modules","dist","build","target","bin","obj","coverage",".next",".nuxt",".venv","venv","__pycache__"}
SOURCE_EXTENSIONS={".js",".jsx",".ts",".tsx",".json",".yaml",".yml",".prisma",".sql",".md",".env"}

DEFAULT_CONFIG={
 "agent":{"name":"qaira-semantic-compiler-platform","version":"v58","mode":"prebuild"},
 "paths":{"source_dir":"/repo","output_dir":"/output","learning_dir":"/learning","changed_files":""},
 "logging":{"verbose_console":True},
 "parsing":{"prefer_tree_sitter":True,"fallback_regex_parser":True,"max_file_size_kb":4096},
 "semantic_compiler":{"inline_fastify_handlers":True,"inline_express_handlers":True,"fastify_schema_extraction":True,"request_body_alias_tracking":True,"request_body_field_usage":True,"response_taint_enabled":True,"auth_scope_enabled":True,"orm_sink_enabled":True,"event_discovery_enabled":True},
 "llm":{"enabled":False,"provider":"openai","model":"gpt-4.1-mini","api_key_env":"OPENAI_API_KEY","endpoint":"https://api.openai.com/v1/chat/completions","temperature":0,"max_tokens":1200,"timeout_seconds":60,"max_retries":2,"max_semantic_slice_lines":120,"include_attempt_history":True,"include_graph_evidence":True,"include_import_evidence":True,"include_orm_evidence":True,"require_json_response":True,"allow_full_file_context":False,"allow_full_repo_context":False}
}

@dataclass
class Contract:
    api_id:str
    method:str
    path:str
    request_body:Dict[str,Any]
    response_body:Dict[str,Any]
    auth:Dict[str,Any]
    source_mappings:Dict[str,List[str]]
    confidence:Dict[str,Any]
    trace:List[Dict[str,Any]]
    request_trace:List[Dict[str,Any]]
    response_trace:List[Dict[str,Any]]
    parameters:List[Dict[str,Any]]=None
    request_context:Dict[str,Any]=None
    curl:str=""

def utc_now(): return datetime.now(timezone.utc).isoformat()
def safe_json(x):
    if hasattr(x,"__dataclass_fields__"): return asdict(x)
    if isinstance(x,Path): return str(x)
    if isinstance(x,list): return [safe_json(i) for i in x]
    if isinstance(x,dict): return {str(k):safe_json(v) for k,v in x.items()}
    return x
def deep_merge(a,b):
    out=dict(a)
    for k,v in (b or {}).items():
        out[k]=deep_merge(out[k],v) if isinstance(v,dict) and isinstance(out.get(k),dict) else v
    return out
def load_config(path):
    cfg=dict(DEFAULT_CONFIG); report={"loaded":False,"errors":[]}
    if path and path.exists():
        try:
            if yaml is None: raise RuntimeError("PyYAML unavailable")
            cfg=deep_merge(DEFAULT_CONFIG,yaml.safe_load(path.read_text(encoding="utf-8",errors="ignore")) or {})
            report["loaded"]=True
        except Exception as e:
            report["errors"].append(str(e))
    return cfg,report
def norm_path(p):
    p=str(p).strip().strip("'\"`")
    if "://" in p: p=re.sub(r"^https?://[^/]+","",p)
    p=re.sub(r":\w+|\$\{[^}]+\}|<[^>]+>","{id}",p.split("?")[0])
    if not p.startswith("/"): p="/"+p
    return re.sub(r"/+","/",p)
def api_id(method,path): return method.lower()+"-"+(re.sub(r"[^A-Za-z0-9]+","-",path.strip("/")).strip("-") or "root")
def line_no(t,i): return t[:i].count("\n")+1
def sha(x): return hashlib.sha256(str(x).encode("utf-8","ignore")).hexdigest()
def sample(schema): return {k:"sample" for k in (schema.get("properties",{}) if schema else {})}
def node(id,label,props): return {"id":id,"label":label,"properties":props}
def edge(a,b,t,props=None): return {"from":a,"to":b,"type":t,"properties":props or {}}
def headers(auth):
    h={"Content-Type":"application/json"}
    if auth.get("required"): h["Authorization"]="Bearer {{token}}"
    return h
def make_curl(c):
    parts=[f"curl -X {c.method} '{{{{baseUrl}}}}{c.path}'"]
    for k,v in headers(c.auth).items(): parts.append(f"-H '{k}: {v}'")
    if c.request_body: parts.append("-d '"+json.dumps(sample(c.request_body))+"'")
    return " \\\n  ".join(parts)
def text_of(src,node): return src[node.start_byte:node.end_byte].decode("utf-8",errors="ignore")
def node_line(n): return n.start_point[0]+1 if hasattr(n,"start_point") else 1

class Logger:
    def __init__(self,out,cfg):
        self.out=out; self.verbose=cfg.get("logging",{}).get("verbose_console",True)
        self.logs=out/"logs"; self.logs.mkdir(parents=True,exist_ok=True)
        self.text=self.logs/"qaira_verbose.log"
    def info(self,stage,msg,**data):
        line=f"[{utc_now()}] [INFO] [{stage}] {msg} {json.dumps(safe_json(data),ensure_ascii=False)}"
        self.text.open("a",encoding="utf-8").write(line+"\n")
        if self.verbose: print(line)

class Store:
    def __init__(self,out,log):
        self.out=out; self.log=log
        for d in ["repository","ast","orm","graph","trace","auth","events","impact","llm","discovery","generated","summary","logs","config","diagnostics"]:
            (out/d).mkdir(parents=True,exist_ok=True)
    def json(self,rel,data):
        p=self.out/rel; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(safe_json(data),indent=2,ensure_ascii=False),encoding="utf-8")
        self.log.info("store","wrote json",file=rel)
    def text(self,rel,data):
        p=self.out/rel; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(data,encoding="utf-8")
        self.log.info("store","wrote text",file=rel)

class FS:
    def __init__(self,src,changed=None,max_kb=4096):
        self.src=src.resolve(); self.max=max_kb*1024
        self.changed=set([x.strip().replace("\\","/").lstrip("./") for x in (changed or []) if x.strip()])
    def all_files(self):
        for root,dirs,files in os.walk(self.src):
            dirs[:]=[d for d in dirs if d not in EXCLUDED_DIRS]
            for n in files:
                p=Path(root)/n
                if p.exists() and p.stat().st_size <= self.max and (p.suffix.lower() in SOURCE_EXTENSIONS or p.name in {"package.json","Dockerfile"}):
                    yield p
    def rel(self,p):
        try: return str(p.resolve().relative_to(self.src)).replace("\\","/")
        except Exception: return str(p)
    def read(self,p): return p.read_text(encoding="utf-8",errors="ignore")
    def resolve_import_path(self,from_file,module):
        if not hasattr(self,"_enterprise_module_resolver"):
            self._enterprise_module_resolver=EnterpriseModuleResolverV51({})
            self._enterprise_module_resolver.initialize(self)
        return self._enterprise_module_resolver.resolve(self,from_file,module)

    def fingerprint(self):
        h=hashlib.sha256(); files=[]
        for p in self.all_files():
            r=self.rel(p); b=p.read_bytes(); fh=hashlib.sha256(b).hexdigest()
            h.update(r.encode()); h.update(fh.encode())
            files.append({"file":r,"sha256":fh,"changed":r in self.changed,"sizeBytes":len(b)})
        return {"repositoryHash":h.hexdigest(),"fileCount":len(files),"scannedAt":utc_now()},files

class OrmSinkAgent:
    def run(self,fs):
        models=[]; fields=[]
        for p in fs.all_files():
            r=fs.rel(p); t=fs.read(p); low=r.lower()
            if p.suffix.lower()==".prisma" or "schema.prisma" in low:
                ms,fs2=self.parse_prisma(t,r); models+=ms; fields+=fs2
            if p.suffix.lower()==".sql":
                ms,fs2=self.parse_sql(t,r); models+=ms; fields+=fs2
        graph={"nodes":[],"edges":[]}
        for m in models: graph["nodes"].append(node("orm_model:"+m["name"],"OrmModel",m))
        for f in fields:
            fid=f"orm_field:{f['model']}:{f['name']}"
            graph["nodes"].append(node(fid,"OrmField",f)); graph["edges"].append(edge("orm_model:"+f["model"],fid,"HAS_FIELD",f))
        return {"models":models,"fields":fields},{"rules":self.validation_rules(fields)},graph
    def parse_prisma(self,t,r):
        models=[]; fields=[]
        for mm in re.finditer(r"model\s+(\w+)\s*\{([\s\S]*?)\}",t):
            model=mm.group(1); models.append({"name":model,"orm":"prisma","file":r,"line":line_no(t,mm.start())})
            for line in mm.group(2).splitlines():
                s=line.strip()
                if not s or s.startswith("//") or s.startswith("@@"): continue
                parts=s.split()
                if len(parts)>=2:
                    fields.append({"model":model,"name":parts[0],"type":self.type_map(parts[1]),"rawType":parts[1],"required":"?" not in parts[1],"unique":"@unique" in s,"id":"@id" in s,"default":"@default" in s,"source":r})
        return models,fields
    def parse_sql(self,t,r):
        models=[]; fields=[]
        for mm in re.finditer(r"CREATE\s+TABLE\s+[`\"]?(\w+)[`\"]?\s*\(([\s\S]*?)\);",t,re.I):
            model=self.camel(mm.group(1)); models.append({"name":model,"orm":"sql","file":r,"line":line_no(t,mm.start())})
            for line in mm.group(2).splitlines():
                s=line.strip().rstrip(",")
                m=re.match(r"[`\"]?(\w+)[`\"]?\s+([A-Z]+)(?:\((\d+)\))?",s,re.I)
                if m:
                    fields.append({"model":model,"name":m.group(1),"type":self.type_map(m.group(2)),"maxLength":int(m.group(3)) if m.group(3) else None,"required":"NOT NULL" in s.upper(),"unique":"UNIQUE" in s.upper(),"id":"PRIMARY KEY" in s.upper(),"source":r})
        return models,fields
    def validation_rules(self,fields):
        out=[]
        for f in fields:
            d={"model":f["model"],"field":f["name"],"type":f["type"],"required":f.get("required",False),"unique":f.get("unique",False),"id":f.get("id",False),"source":f.get("source")}
            if f.get("maxLength"): d["maxLength"]=f["maxLength"]
            out.append(d)
        return out
    def type_map(self,t):
        low=str(t).lower().replace("?","").replace("[]","")
        if any(x in low for x in ["int","float","decimal","double","number","bigint"]): return "number"
        if "bool" in low: return "boolean"
        if any(x in low for x in ["date","time"]): return "string"
        if any(x in low for x in ["json","object"]): return "object"
        return "string"
    def camel(self,s): return "".join(x[:1].upper()+x[1:] for x in re.split(r"[_\-\s]+",str(s)) if x)


class TypeInferencer:
    def __init__(self,cfg):
        ve=cfg.get("validation_engine",{})
        self.arr=ve.get("infer_arrays_by_name",True)
        self.bool=ve.get("infer_booleans_by_name",True)
        self.num=ve.get("infer_numbers_by_name",True)
    def infer(self,name,raw=""):
        n=str(name).lower()
        r=str(raw).lower()
        if "array" in r or "[]" in r or ".array" in r or "type.array" in r or (self.arr and (n.endswith("_ids") or n.endswith("ids") or n.endswith("list") or n.endswith("items") or n.endswith("roles") or n.endswith("_keys"))):
            return {"type":"array","items":{"type":"string"}}
        if "boolean" in r or "bool" in r or "z.boolean" in r or "joi.boolean" in r or "type.boolean" in r or (self.bool and (n.startswith("is_") or n.startswith("has_") or n.startswith("can_") or n.startswith("enable") or n.startswith("allow") or n.startswith("should_"))):
            return {"type":"boolean"}
        if any(x in r for x in ["number","integer","int","float","double","decimal"]) or (self.num and (n.endswith("_count") or n in {"age","count","limit","offset","page","size","priority","order","duration"})):
            return {"type":"number"}
        if "object" in r or "record" in r:
            return {"type":"object"}
        return {"type":"string"}


class ValidationSchemaEngine:
    def __init__(self,cfg):
        self.cfg=cfg
        self.inf=TypeInferencer(cfg)
    def run(self,fs):
        schemas=[]; dtos=[]; type_registry=[]; plugin_report={}
        for p in fs.all_files():
            if p.suffix.lower() not in {".ts",".tsx",".js",".jsx",".py",".java",".cs",".go"}:
                continue
            r=fs.rel(p); t=fs.read(p)
            found=[]
            found += self.extract_zod(t,r)
            found += self.extract_joi(t,r)
            found += self.extract_typebox(t,r)
            found += self.extract_yup(t,r)
            found += self.extract_ts_dto(t,r)
            found += self.extract_ts_type_alias(t,r)
            found += self.extract_class_validator(t,r)
            schemas += found
            dtos += [x for x in found if x.get("kind") in {"typescript_interface","typescript_class","typescript_type_alias","class_validator"}]
            type_registry += [{"name":x["name"],"file":x["file"],"kind":x["kind"],"schema":x["schema"],"fields":x.get("fields",[])} for x in found]
            plugin_report[r]={"schemas":len(found),"plugins":sorted(set([x["kind"] for x in found]))}
        return {"schemas":schemas},{"dtos":dtos},{"types":type_registry},{"files":plugin_report}
    def schema_obj(self,name,kind,file,line,fields,source):
        props={}; req=[]
        for f in fields:
            field=f["name"]; raw=f.get("raw","")
            s=self.inf.infer(field,raw); s["x-qaira-source"]=source
            props[field]=s
            if f.get("required",True): req.append(field)
        return {"name":name,"kind":kind,"file":file,"line":line,"schema":{"type":"object","required":sorted(set(req)),"properties":props},"fields":fields}
    def extract_zod(self,t,r):
        out=[]
        for m in re.finditer(r"(?:const|export\s+const)\s+(\w+)\s*=\s*z\.object\s*\(\s*\{([\s\S]*?)\}\s*\)",t):
            fields=[]
            for fm in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([^,\n}]+)",m.group(2)):
                raw=fm.group(2); fields.append({"name":fm.group(1),"raw":raw,"required":".optional" not in raw})
            out.append(self.schema_obj(m.group(1),"zod",r,line_no(t,m.start()),fields,"zod"))
        return out
    def extract_joi(self,t,r):
        out=[]
        for m in re.finditer(r"(?:const|export\s+const)\s+(\w+)\s*=\s*Joi\.object\s*\(\s*\{([\s\S]*?)\}\s*\)",t):
            fields=[]
            for fm in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([^,\n}]+)",m.group(2)):
                raw=fm.group(2); fields.append({"name":fm.group(1),"raw":raw,"required":".required" in raw})
            out.append(self.schema_obj(m.group(1),"joi",r,line_no(t,m.start()),fields,"joi"))
        return out
    def extract_typebox(self,t,r):
        out=[]
        for m in re.finditer(r"(?:const|export\s+const)\s+(\w+)\s*=\s*Type\.Object\s*\(\s*\{([\s\S]*?)\}\s*\)",t):
            fields=[]
            for fm in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([^,\n}]+)",m.group(2)):
                raw=fm.group(2); fields.append({"name":fm.group(1),"raw":raw,"required":"Optional" not in raw})
            out.append(self.schema_obj(m.group(1),"typebox",r,line_no(t,m.start()),fields,"typebox"))
        return out
    def extract_yup(self,t,r):
        out=[]
        for m in re.finditer(r"(?:const|export\s+const)\s+(\w+)\s*=\s*yup\.object\s*\(\s*\{([\s\S]*?)\}\s*\)",t):
            fields=[]
            for fm in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([^,\n}]+)",m.group(2)):
                raw=fm.group(2); fields.append({"name":fm.group(1),"raw":raw,"required":".required" in raw})
            out.append(self.schema_obj(m.group(1),"yup",r,line_no(t,m.start()),fields,"yup"))
        return out
    def extract_ts_dto(self,t,r):
        out=[]
        for m in re.finditer(r"(?:export\s+)?interface\s+(\w+)\s*(?:extends\s+[^{]+)?\s*\{([\s\S]*?)\}",t):
            fields=self.extract_ts_fields(m.group(2))
            out.append(self.schema_obj(m.group(1),"typescript_interface",r,line_no(t,m.start()),fields,"typescript_interface"))
        for m in re.finditer(r"(?:export\s+)?class\s+(\w*(?:Dto|DTO|Request|Input|Payload|Body|Command|Query)?\w*)\s*\{([\s\S]*?)\}",t):
            body=m.group(2)
            # Avoid treating arbitrary classes with methods only as DTOs
            fields=self.extract_ts_fields(body)
            if fields:
                out.append(self.schema_obj(m.group(1),"typescript_class",r,line_no(t,m.start()),fields,"typescript_class"))
        return out
    def extract_ts_type_alias(self,t,r):
        out=[]
        # type LoginRequest = { email: string; password: string }
        for m in re.finditer(r"(?:export\s+)?type\s+(\w+)\s*=\s*\{([\s\S]*?)\}",t):
            fields=self.extract_ts_fields(m.group(2))
            if fields:
                out.append(self.schema_obj(m.group(1),"typescript_type_alias",r,line_no(t,m.start()),fields,"typescript_type_alias"))
        # type LoginRequest = Pick<User, 'email' | 'password'> or Partial<User>
        for m in re.finditer(r"(?:export\s+)?type\s+(\w+)\s*=\s*([^;\n]+)",t):
            name=m.group(1); raw=m.group(2)
            if "{" in raw: continue
            fields=[]
            # Store wrapper as pseudo-field evidence, actual wrapper resolution done in TypeResolutionEngine
            out.append({"name":name,"kind":"typescript_type_alias","file":r,"line":line_no(t,m.start()),"schema":{"type":"object","required":[],"properties":{},"x-qaira-alias-raw":raw.strip()},"fields":fields,"aliasRaw":raw.strip()})
        return out
    def extract_ts_fields(self,body):
        fields=[]
        # supports both semicolon and newline style
        for fm in re.finditer(r"([A-Za-z_$][\w$]*)\??\s*:\s*([^;\n,}]+)",body):
            fields.append({"name":fm.group(1),"raw":fm.group(2).strip(),"required":"?" not in fm.group(0)})
        return fields
    def extract_class_validator(self,t,r):
        out=[]
        for m in re.finditer(r"(?:export\s+)?class\s+(\w+)\s*\{([\s\S]*?)\}",t):
            body=m.group(2)
            if not re.search(r"@Is\w+|@Length|@Min|@Max|@IsOptional",body): continue
            fields=[]
            for fm in re.finditer(r"((?:@\w+(?:\([^)]*\))?\s*)+)\s*([A-Za-z_$][\w$]*)\??\s*:\s*([^;\n]+)",body):
                decorators=fm.group(1)
                fields.append({"name":fm.group(2),"raw":fm.group(3)+" "+decorators,"required":"@IsOptional" not in decorators})
            out.append(self.schema_obj(m.group(1),"class_validator",r,line_no(t,m.start()),fields,"class_validator"))
        return out



class EnterpriseModuleResolverV51:
    def __init__(self,cfg):
        self.cfg=cfg
        self.extensions=[".js",".jsx",".ts",".tsx",".mjs",".cjs",".json"]
        self.index_names=["index.js","index.jsx","index.ts","index.tsx","index.mjs","index.cjs"]
        self.report=[]
        self.registry=[]
        self.execution_trace=[]
        self.audit={"imports_discovered":0,"imports_attempted":0,"imports_resolved":0,"imports_unresolved":0,"calls":[]}
        self.tsconfigs=[]
        self.package_index={}
        self.workspace_roots=[]
    def initialize(self,fs):
        self.tsconfigs=self.load_tsconfigs(fs)
        self.package_index=self.index_packages(fs)
        self.workspace_roots=self.find_workspace_roots(fs)
        self.report.append({
            "stage":"initialize",
            "tsconfigs":len(self.tsconfigs),
            "packages":len(self.package_index),
            "workspaceRoots":len(self.workspace_roots)
        })
    def resolve(self,fs,from_file,module):
        if not module:
            return ""
        if not self.tsconfigs and not self.package_index:
            self.initialize(fs)
        attempts=[]
        # 1 relative import
        if str(module).startswith("."):
            resolved=self.resolve_relative(fs,from_file,module,attempts)
            return self.done(from_file,module,resolved,attempts)
        # 2 tsconfig/jsconfig aliases
        resolved=self.resolve_alias(fs,from_file,module,attempts)
        if resolved:
            return self.done(from_file,module,resolved,attempts)
        # 3 package / workspace
        resolved=self.resolve_package(fs,module,attempts)
        if resolved:
            return self.done(from_file,module,resolved,attempts)
        return self.done(from_file,module,"",attempts)
    def done(self,from_file,module,resolved,attempts):
        item={"fromFile":from_file,"module":module,"resolver":"enterprise","attempted":True,"resolvedFile":resolved,"resolved":bool(resolved),"attempts":attempts[:80]}
        self.registry.append(item)
        self.execution_trace.append(item)
        self.audit["imports_attempted"]+=1
        if resolved:
            self.audit["imports_resolved"]+=1
        else:
            self.audit["imports_unresolved"]+=1
        self.audit["calls"].append({"fromFile":from_file,"module":module,"resolved":bool(resolved),"resolvedFile":resolved})
        return resolved
    def resolve_relative(self,fs,from_file,module,attempts):
        base=(fs.src/from_file).parent
        raw=(base/module).resolve()
        return self.resolve_candidate_path(fs,raw,attempts)
    def resolve_candidate_path(self,fs,raw,attempts):
        candidates=[]
        raw=Path(raw)
        # exact file
        candidates.append(raw)
        # extension variants
        for ext in self.extensions:
            candidates.append(raw.with_suffix(ext))
        # directory package.json and index
        if raw.exists() and raw.is_dir():
            candidates += self.package_entry_candidates(raw)
            for name in self.index_names:
                candidates.append(raw/name)
        else:
            for name in self.index_names:
                candidates.append(raw/name)
        for c in candidates:
            attempts.append(str(c))
            if c.exists() and c.is_file():
                try:
                    return str(c.resolve().relative_to(fs.src)).replace("\\","/")
                except Exception:
                    return str(c)
        return ""
    def package_entry_candidates(self,dir_path):
        out=[]
        pkg=dir_path/"package.json"
        if pkg.exists():
            try:
                data=json.loads(pkg.read_text(encoding="utf-8",errors="ignore"))
                for key in ["module","main","browser"]:
                    if isinstance(data.get(key),str):
                        out.append(dir_path/data[key])
                exp=data.get("exports")
                if isinstance(exp,str):
                    out.append(dir_path/exp)
                elif isinstance(exp,dict):
                    root=exp.get(".")
                    if isinstance(root,str):
                        out.append(dir_path/root)
                    elif isinstance(root,dict):
                        for k in ["import","require","default"]:
                            if isinstance(root.get(k),str):
                                out.append(dir_path/root[k])
            except Exception:
                pass
        return out
    def load_tsconfigs(self,fs):
        configs=[]
        for name in ["tsconfig.json","jsconfig.json"]:
            for p in fs.src.rglob(name):
                try:
                    data=json.loads(p.read_text(encoding="utf-8",errors="ignore"))
                    compiler=data.get("compilerOptions",{})
                    configs.append({
                        "file":str(p.relative_to(fs.src)).replace("\\","/"),
                        "dir":p.parent,
                        "baseUrl":compiler.get("baseUrl","."),
                        "paths":compiler.get("paths",{})
                    })
                except Exception:
                    pass
        return configs
    def resolve_alias(self,fs,from_file,module,attempts):
        for cfg in self.tsconfigs:
            base=(cfg["dir"]/cfg.get("baseUrl",".")).resolve()
            paths=cfg.get("paths") or {}
            for alias,targets in paths.items():
                aliases=targets if isinstance(targets,list) else [targets]
                if "*" in alias:
                    prefix=alias.split("*")[0]
                    suffix=alias.split("*")[-1]
                    if module.startswith(prefix) and module.endswith(suffix):
                        star=module[len(prefix):len(module)-len(suffix) if suffix else None]
                        for target in aliases:
                            candidate=str(target).replace("*",star)
                            resolved=self.resolve_candidate_path(fs,(base/candidate).resolve(),attempts)
                            if resolved:
                                return resolved
                elif module==alias or module.startswith(alias+"/"):
                    rest=module[len(alias):].lstrip("/")
                    for target in aliases:
                        candidate=str(target).replace("*",rest)
                        resolved=self.resolve_candidate_path(fs,(base/candidate).resolve(),attempts)
                        if resolved:
                            return resolved
            # Common aliases even if paths missing
            for prefix in ["@/","@api/","@src/","src/"]:
                if module.startswith(prefix):
                    rest=module[len(prefix):]
                    resolved=self.resolve_candidate_path(fs,(base/rest).resolve(),attempts)
                    if resolved:
                        return resolved
        # fallback common repo roots
        for root_name in ["src","backend/api/src","backend/src","api/src"]:
            root=(fs.src/root_name)
            if root.exists():
                for prefix in ["@/","@api/","@src/","src/"]:
                    if module.startswith(prefix):
                        rest=module[len(prefix):]
                        resolved=self.resolve_candidate_path(fs,(root/rest).resolve(),attempts)
                        if resolved:
                            return resolved
        return ""
    def index_packages(self,fs):
        index={}
        for p in fs.src.rglob("package.json"):
            if "node_modules" in str(p):
                continue
            try:
                data=json.loads(p.read_text(encoding="utf-8",errors="ignore"))
                name=data.get("name")
                if name:
                    index[name]={"dir":p.parent,"package":data}
            except Exception:
                pass
        return index
    def find_workspace_roots(self,fs):
        roots=[]
        for p in fs.src.rglob("package.json"):
            if "node_modules" in str(p):
                continue
            try:
                data=json.loads(p.read_text(encoding="utf-8",errors="ignore"))
                if data.get("workspaces"):
                    roots.append(p.parent)
            except Exception:
                pass
        for name in ["pnpm-workspace.yaml","turbo.json","nx.json"]:
            for p in fs.src.rglob(name):
                if "node_modules" not in str(p):
                    roots.append(p.parent)
        return list(dict.fromkeys(roots))
    def resolve_package(self,fs,module,attempts):
        # exact package
        if module in self.package_index:
            pkg=self.package_index[module]
            for c in self.package_entry_candidates(pkg["dir"]):
                resolved=self.resolve_candidate_path(fs,c.resolve(),attempts)
                if resolved: return resolved
            resolved=self.resolve_candidate_path(fs,pkg["dir"].resolve(),attempts)
            if resolved: return resolved
        # package subpath
        parts=module.split("/")
        pkg_name="/".join(parts[:2]) if module.startswith("@") and len(parts)>=2 else parts[0]
        rest="/".join(parts[2:] if module.startswith("@") else parts[1:])
        if pkg_name in self.package_index:
            root=self.package_index[pkg_name]["dir"]
            resolved=self.resolve_candidate_path(fs,(root/rest).resolve(),attempts)
            if resolved: return resolved
        return ""



class ImportRegistryHydratorV52:
    def __init__(self,cfg,enterprise_resolver):
        self.cfg=cfg
        self.enterprise_resolver=enterprise_resolver
        self.audit=[]
        self.diagnostics={
            "importsChecked":0,
            "exportsChecked":0,
            "alreadyResolved":0,
            "hydrated":0,
            "stillUnresolved":0,
            "missingModule":0
        }
    def hydrate(self,fs,import_registry):
        imports=import_registry.get("imports",[]) or []
        exports=import_registry.get("exports",[]) or []
        hydrated_imports=[]
        hydrated_exports=[]
        for item in imports:
            hydrated_imports.append(self.hydrate_item(fs,item,"import"))
        for item in exports:
            hydrated_exports.append(self.hydrate_item(fs,item,"export"))
        new_registry=dict(import_registry)
        new_registry["imports"]=hydrated_imports
        new_registry["exports"]=hydrated_exports
        new_registry["hydrationAudit"]=self.audit
        new_registry["hydrationDiagnostics"]=self.diagnostics
        return new_registry
    def hydrate_item(self,fs,item,kind):
        self.diagnostics["importsChecked" if kind=="import" else "exportsChecked"]+=1
        before=item.get("resolvedFile","")
        module=item.get("module","")
        file=item.get("file","")
        after=before
        resolver_result=""
        if before:
            self.diagnostics["alreadyResolved"]+=1
        elif module and file:
            resolver_result=self.enterprise_resolver.resolve(fs,file,module)
            if resolver_result:
                after=resolver_result
                item=dict(item)
                item["resolvedFile"]=after
                item["x-qaira-hydrated-resolvedFile"]=True
                self.diagnostics["hydrated"]+=1
            else:
                self.diagnostics["stillUnresolved"]+=1
        else:
            self.diagnostics["missingModule"]+=1
        audit_item={
            "kind":kind,
            "file":file,
            "module":module,
            "beforeResolvedFile":before,
            "resolverResult":resolver_result,
            "afterResolvedFile":after,
            "hydrated":bool((not before) and after),
            "alreadyResolved":bool(before),
            "stillUnresolved":not bool(after),
        }
        self.audit.append(audit_item)
        return item


class ImportGraphResolver:
    def __init__(self,cfg,enterprise_resolver=None):
        self.cfg=cfg
        self.enterprise_resolver=enterprise_resolver or EnterpriseModuleResolverV51(cfg)
        self.import_discovery_trace=[]
    def run(self,fs):
        imports=[]; exports=[]; files=[]
        for p in fs.all_files():
            if p.suffix.lower() not in {".ts",".tsx",".js",".jsx"}:
                continue
            r=fs.rel(p); t=fs.read(p)
            files.append(r)
            imports += self.extract_imports(t,r,fs)
            imports += self.extract_commonjs_requires(t,r,fs)
            exports += self.extract_exports(t,r,fs)
            exports += self.extract_commonjs_exports(t,r,fs)
        self.enterprise_resolver.audit["imports_discovered"]=len(imports)+len(exports)
        for i in imports:
            self.import_discovery_trace.append({"kind":"import","file":i.get("file"),"module":i.get("module"),"resolvedFile":i.get("resolvedFile"),"attempted":True,"resolver":"enterprise"})
        for e in exports:
            self.import_discovery_trace.append({"kind":"export","file":e.get("file"),"module":e.get("module"),"resolvedFile":e.get("resolvedFile"),"attempted":bool(e.get("module")),"resolver":"enterprise"})
        graph={
            "nodes":[node("file:"+f,"File",{"file":f}) for f in files],
            "edges":[edge("file:"+i["file"],"file:"+i["resolvedFile"],"IMPORTS",i) for i in imports if i.get("resolvedFile")]
                    + [edge("file:"+e["file"],"file:"+e["resolvedFile"],"RE_EXPORTS",e) for e in exports if e.get("resolvedFile")]
        }
        return {"imports":imports,"exports":exports,"graph":graph,"resolverAudit":self.enterprise_resolver.audit,"resolverExecutionTrace":self.enterprise_resolver.execution_trace,"importDiscoveryTrace":self.import_discovery_trace}
    def extract_imports(self,t,r,fs):
        out=[]
        for im in re.finditer(r"import\s+([\s\S]*?)\s+from\s+['\"]([^'\"]+)['\"]",t):
            raw=im.group(1).strip()
            module=im.group(2)
            resolved=self.resolve_path(fs,r,module)
            if raw.startswith("* as"):
                out.append({"file":r,"module":module,"resolvedFile":resolved,"local":raw.split()[-1],"imported":"*","kind":"namespace"})
            elif "{" in raw:
                prefix=raw[:raw.find("{")].strip().strip(",")
                if prefix:
                    out.append({"file":r,"module":module,"resolvedFile":resolved,"local":prefix,"imported":"default","kind":"default"})
                named=raw[raw.find("{")+1:raw.find("}")]
                for part in named.split(","):
                    part=part.strip()
                    if not part: continue
                    if " as " in part:
                        imported,local=[x.strip() for x in part.split(" as ",1)]
                    else:
                        imported=local=part
                    out.append({"file":r,"module":module,"resolvedFile":resolved,"local":local,"imported":imported,"kind":"named"})
            else:
                local=raw.split(",")[0].strip()
                if local:
                    out.append({"file":r,"module":module,"resolvedFile":resolved,"local":local,"imported":"default","kind":"default"})
        return out
    def extract_commonjs_requires(self,t,r,fs):
        out=[]
        # const service = require('./service')
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",t):
            local=m.group(1); module=m.group(2); resolved=self.resolve_path(fs,r,module)
            out.append({"file":r,"module":module,"resolvedFile":resolved,"local":local,"imported":"module.exports","kind":"commonjs_default_require"})
        # const { create, update: updateUser } = require('./service')
        for m in re.finditer(r"(?:const|let|var)\s*\{([\s\S]*?)\}\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",t):
            module=m.group(2); resolved=self.resolve_path(fs,r,module)
            for part in m.group(1).split(","):
                part=part.strip()
                if not part: continue
                if ":" in part:
                    imported,local=[x.strip() for x in part.split(":",1)]
                else:
                    imported=local=part
                out.append({"file":r,"module":module,"resolvedFile":resolved,"local":local,"imported":imported,"kind":"commonjs_destructured_require"})
        # import-like TS compiled style: const service_1 = require(...)
        return out
    def extract_exports(self,t,r,fs):
        out=[]
        for ex in re.finditer(r"export\s+\*\s+from\s+['\"]([^'\"]+)['\"]",t):
            module=ex.group(1)
            out.append({"file":r,"module":module,"resolvedFile":self.resolve_path(fs,r,module),"kind":"re_export_all"})
        for ex in re.finditer(r"export\s+\{([\s\S]*?)\}\s+from\s+['\"]([^'\"]+)['\"]",t):
            module=ex.group(2); resolved=self.resolve_path(fs,r,module)
            for part in ex.group(1).split(","):
                part=part.strip()
                if not part: continue
                if " as " in part:
                    exported,local=[x.strip() for x in part.split(" as ",1)]
                else:
                    exported=local=part
                out.append({"file":r,"module":module,"resolvedFile":resolved,"exported":exported,"local":local,"kind":"re_export_named"})
        # export default { create, update }
        for ex in re.finditer(r"export\s+default\s+\{([\s\S]*?)\}",t):
            for item in ex.group(1).split(","):
                raw=item.strip()
                if not raw: continue
                if ":" in raw:
                    exported,local=[x.strip() for x in raw.split(":",1)]
                else:
                    exported=local=raw
                if re.match(r"^[A-Za-z_$][\w$]*$",local):
                    out.append({"file":r,"exported":exported,"local":local,"kind":"es_default_object_export"})
        # export const service = { create, update }
        for ex in re.finditer(r"export\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*\{([\s\S]*?)\}",t):
            service=ex.group(1)
            for item in ex.group(2).split(","):
                raw=item.strip()
                if not raw: continue
                if ":" in raw:
                    exported,local=[x.strip() for x in raw.split(":",1)]
                else:
                    exported=local=raw
                if re.match(r"^[A-Za-z_$][\w$]*$",local):
                    out.append({"file":r,"exported":exported,"local":local,"serviceObject":service,"kind":"es_named_object_export"})
        return out
    def extract_commonjs_exports(self,t,r,fs):
        out=[]
        # module.exports = { create, update: updateUser }
        for ex in re.finditer(r"module\.exports\s*=\s*\{([\s\S]*?)\}",t):
            for item in ex.group(1).split(","):
                raw=item.strip()
                if not raw: continue
                if ":" in raw:
                    exported,local=[x.strip() for x in raw.split(":",1)]
                else:
                    exported=local=raw
                local=re.sub(r"\s.*$","",local).strip()
                if re.match(r"^[A-Za-z_$][\w$]*$",local):
                    out.append({"file":r,"exported":exported,"local":local,"kind":"commonjs_module_exports_object"})
        # module.exports = serviceObject
        for ex in re.finditer(r"module\.exports\s*=\s*([A-Za-z_$][\w$]*)",t):
            out.append({"file":r,"exported":"module.exports","local":ex.group(1),"kind":"commonjs_module_exports_identifier"})
        # exports.create = create
        for ex in re.finditer(r"exports\.([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)",t):
            out.append({"file":r,"exported":ex.group(1),"local":ex.group(2),"kind":"commonjs_exports_property"})
        # module.exports.create = create
        for ex in re.finditer(r"module\.exports\.([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)",t):
            out.append({"file":r,"exported":ex.group(1),"local":ex.group(2),"kind":"commonjs_module_exports_property"})
        return out
    def resolve_path(self,fs,from_file,module):
        return self.enterprise_resolver.resolve(fs,from_file,module)


class FunctionSignatureRegistry:
    def __init__(self,cfg):
        self.cfg=cfg
        self.diagnostics=[]
    def run(self,fs):
        signatures=[]
        for p in fs.all_files():
            if p.suffix.lower() not in {".ts",".tsx",".js",".jsx"}:
                continue
            r=fs.rel(p); t=fs.read(p)
            before=len(signatures)
            signatures += self.extract_functions(t,r)
            signatures += self.extract_arrow_functions(t,r)
            signatures += self.extract_typed_arrow_functions(t,r)
            signatures += self.extract_property_arrow_functions(t,r)
            signatures += self.extract_object_exports(t,r)
            signatures += self.extract_class_methods(t,r)
            signatures += self.extract_object_literal_methods(t,r)
            signatures += self.extract_handler_type_alias_usage(t,r)
            self.diagnostics.append({"file":r,"signatures":len(signatures)-before})
        # de-duplicate by file/name/line/kind/params
        seen=set(); unique=[]
        for s in signatures:
            key=(s.get("file"),s.get("name"),s.get("qualifiedName"),s.get("line"),json.dumps(s.get("params",[]),sort_keys=True))
            if key not in seen:
                seen.add(key); unique.append(s)
        return {"signatures":unique,"diagnostics":self.diagnostics}
    def normalize_params(self,params):
        params=params.strip()
        params=re.sub(r"//.*","",params)
        params=re.sub(r"/\*[\s\S]*?\*/","",params)
        return params
    def split_params(self,params):
        params=self.normalize_params(params)
        out=[]; cur=[]; depth=0; quote=None
        for ch in params:
            if quote:
                cur.append(ch)
                if ch==quote: quote=None
                continue
            if ch in {"'",'"',"`"}:
                quote=ch; cur.append(ch); continue
            if ch in "([{<": depth+=1
            elif ch in ")]}>": depth=max(0,depth-1)
            if ch=="," and depth==0:
                s="".join(cur).strip()
                if s: out.append(s)
                cur=[]
            else:
                cur.append(ch)
        s="".join(cur).strip()
        if s: out.append(s)
        return out
    def parse_params(self,params,handler_type=""):
        parsed=[]
        raw_params=self.split_params(params)
        generic_types=self.extract_generic_types(handler_type)
        for idx,raw in enumerate(raw_params):
            clean=raw.split("=")[0].strip()
            clean=re.sub(r"^(public|private|protected|readonly)\s+","",clean)
            # destructured with annotation: { a,b }: CreateDto
            if ":" in clean:
                pname,ptype=clean.split(":",1)
                pname=pname.strip().replace("?","")
                ptype=ptype.strip()
            else:
                pname=clean.replace("?","").strip()
                ptype=""
            if not ptype and idx < len(generic_types):
                ptype=generic_types[idx]
            parsed.append({"name":pname,"type":ptype,"raw":raw})
        # For Handler<CreateDto> where function has no params or untyped params
        if not parsed and generic_types:
            parsed.append({"name":"body","type":generic_types[0],"raw":"<inferred-from-handler-generic>"})
        elif parsed and generic_types and not parsed[0].get("type"):
            parsed[0]["type"]=generic_types[0]
            parsed[0]["raw"]=parsed[0].get("raw","")+" <type-from-handler-generic>"
        return parsed
    def extract_generic_types(self,type_expr):
        if not type_expr: return []
        m=re.search(r"<([\s\S]+)>",type_expr)
        if not m: return []
        inner=m.group(1)
        return self.split_params(inner)
    def sig(self,name,params,file,line,kind,exported=False,handler_type="",qualified=None):
        parsed=self.parse_params(params,handler_type)
        return {"name":name,"qualifiedName":qualified or name,"file":file,"line":line,"kind":kind,"params":parsed,"exported":exported,"handlerType":handler_type}
    def extract_functions(self,t,r):
        out=[]
        # multiline function create(data: Dto)
        for m in re.finditer(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([\s\S]*?)\)\s*(?::\s*([A-Za-z_$][\w$<>\[\]|,\s]+))?\s*\{",t):
            out.append(self.sig(m.group(1),m.group(2),r,line_no(t,m.start()),"function_declaration",exported="export" in m.group(0)))
        return out
    def extract_arrow_functions(self,t,r):
        out=[]
        # const create = async (data: Dto) =>
        for m in re.finditer(r"(?:(export)\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([\s\S]*?)\)\s*(?::\s*([A-Za-z_$][\w$<>\[\]|,\s]+))?\s*=>",t):
            out.append(self.sig(m.group(2),m.group(3),r,line_no(t,m.start()),"arrow_function",exported=bool(m.group(1))))
        # const create = async data =>, not much type info, but keep
        for m in re.finditer(r"(?:(export)\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*async\s+([A-Za-z_$][\w$]*)\s*=>",t):
            out.append(self.sig(m.group(2),m.group(3),r,line_no(t,m.start()),"arrow_function_single_param",exported=bool(m.group(1))))
        return out
    def extract_typed_arrow_functions(self,t,r):
        out=[]
        # const create: Handler<CreateDto> = async (data) =>
        # const create: ServiceHandler<CreateDto, ResponseDto> = async (data, ctx) =>
        for m in re.finditer(r"(?:(export)\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*:\s*([^=;\n]+(?:<[\s\S]*?>)?)\s*=\s*(?:async\s*)?\(([\s\S]*?)\)\s*=>",t):
            out.append(self.sig(m.group(2),m.group(4),r,line_no(t,m.start()),"typed_arrow_function",exported=bool(m.group(1)),handler_type=m.group(3).strip()))
        # const create: Handler<CreateDto> = async data =>
        for m in re.finditer(r"(?:(export)\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*:\s*([^=;\n]+(?:<[\s\S]*?>)?)\s*=\s*async\s+([A-Za-z_$][\w$]*)\s*=>",t):
            out.append(self.sig(m.group(2),m.group(4),r,line_no(t,m.start()),"typed_arrow_single_param",exported=bool(m.group(1)),handler_type=m.group(3).strip()))
        return out
    def extract_property_arrow_functions(self,t,r):
        out=[]
        # save = (dto: SaveDto) => inside object/class
        for m in re.finditer(r"(?:(public|private|protected)\s+)?([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([\s\S]*?)\)\s*=>",t):
            out.append(self.sig(m.group(2),m.group(3),r,line_no(t,m.start()),"property_arrow_function",exported=True))
        # save: Handler<Dto> = async (dto) =>
        for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([^=;\n]+(?:<[\s\S]*?>)?)\s*=\s*(?:async\s*)?\(([\s\S]*?)\)\s*=>",t):
            out.append(self.sig(m.group(1),m.group(3),r,line_no(t,m.start()),"typed_property_arrow_function",exported=True,handler_type=m.group(2).strip()))
        return out
    def extract_object_literal_methods(self,t,r):
        out=[]
        # const service = { create: async (data) => {}, update(data) {} }
        for obj in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\{([\s\S]*?)\n?\}",t):
            obj_name=obj.group(1); body=obj.group(2)
            # create: async (data: Dto) =>
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?\(([\s\S]*?)\)\s*=>",body):
                sig=self.sig(m.group(1),m.group(2),r,line_no(t,obj.start()+m.start()),"object_literal_arrow_method",exported=True,qualified=obj_name+"."+m.group(1))
                sig["serviceObject"]=obj_name
                out.append(sig)
            # create(data) { }
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*\(([\s\S]*?)\)\s*\{",body):
                if m.group(1) in {"if","for","while","switch","catch"}: continue
                sig=self.sig(m.group(1),m.group(2),r,line_no(t,obj.start()+m.start()),"object_literal_method",exported=True,qualified=obj_name+"."+m.group(1))
                sig["serviceObject"]=obj_name
                out.append(sig)
            # create: createKnowledge reference
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$]*)\s*(?:,|$)",body):
                sig={"name":m.group(1),"qualifiedName":obj_name+"."+m.group(1),"file":r,"line":line_no(t,obj.start()+m.start()),"kind":"object_method_reference","params":[],"exported":True,"serviceObject":obj_name,"targetName":m.group(2)}
                out.append(sig)
        return out

    def extract_object_exports(self,t,r):
        out=[]
        # export default { login, create } or module.exports = { login }
        for m in re.finditer(r"(?:export\s+default|module\.exports\s*=)\s*\{([\s\S]*?)\}",t):
            body=m.group(1)
            for item in body.split(","):
                name=item.strip().split(":")[-1].strip()
                if re.match(r"^[A-Za-z_$][\w$]*$",name):
                    out.append({"name":name,"qualifiedName":name,"file":r,"line":line_no(t,m.start()),"kind":"object_export_reference","params":[],"exported":True,"viaDefaultObject":True})
        return out
    def extract_class_methods(self,t,r):
        out=[]
        # more tolerant class body method extraction
        for cm in re.finditer(r"class\s+([A-Za-z_$][\w$]*)[\s\S]*?\{([\s\S]*?)\n\}",t):
            cls=cm.group(1); body=cm.group(2)
            # async create(\n data: Dto,\n ctx: Context\n): Promise<X> {
            for m in re.finditer(r"(?:public|private|protected)?\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(([\s\S]*?)\)\s*(?::\s*([A-Za-z_$][\w$<>\[\]|,\s]+))?\s*\{",body):
                if m.group(1) in {"if","for","while","switch","catch","function"}: continue
                sig=self.sig(m.group(1),m.group(2),r,line_no(t,cm.start()+m.start()),"class_method",exported=True,qualified=cls+"."+m.group(1))
                sig["className"]=cls
                out.append(sig)
            # save = (dto: Dto) =>
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([\s\S]*?)\)\s*=>",body):
                sig=self.sig(m.group(1),m.group(2),r,line_no(t,cm.start()+m.start()),"class_property_arrow",exported=True,qualified=cls+"."+m.group(1))
                sig["className"]=cls
                out.append(sig)
        return out
    def extract_handler_type_alias_usage(self,t,r):
        out=[]
        # export const create: RequestHandler<CreateDto> = handlerFactory(...)
        for m in re.finditer(r"(?:(export)\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$]*(?:<[\s\S]*?>))\s*=",t):
            handler_type=m.group(3).strip()
            if "<" in handler_type:
                out.append(self.sig(m.group(2),"",r,line_no(t,m.start()),"handler_type_variable",exported=bool(m.group(1)),handler_type=handler_type))
        return out

class ServiceCallResolver:
    def __init__(self,signature_registry,import_registry):
        self.signatures=(signature_registry or {}).get("signatures",[])
        self.imports=(import_registry or {}).get("imports",[])
        self.exports=(import_registry or {}).get("exports",[])
        self.resolution_report=[]
    def resolve(self,caller_file,call):
        raw=call or ""
        parts=raw.split(".")
        if len(parts)>=2:
            local=parts[0]
            method=parts[-1]
            imp=self.find_import(caller_file,local)
            if imp:
                target_files=self.resolve_import_target_files(imp)
                for tf in target_files:
                    sig=self.find_signature(tf,method)
                    if sig:
                        self.resolution_report.append({"callerFile":caller_file,"call":raw,"strategy":"import_object_method","import":imp,"signature":sig})
                        return self.follow_reference(sig)
                for tf in target_files:
                    sig=self.find_exported_method(tf,method,imp)
                    if sig:
                        self.resolution_report.append({"callerFile":caller_file,"call":raw,"strategy":"commonjs_or_object_export_method","import":imp,"signature":sig})
                        return self.follow_reference(sig)
                for tf in target_files:
                    sig=self.find_signature_any(tf,method)
                    if sig:
                        self.resolution_report.append({"callerFile":caller_file,"call":raw,"strategy":"default_or_namespace_method","import":imp,"signature":sig})
                        return self.follow_reference(sig)
            self.resolution_report.append({"callerFile":caller_file,"call":raw,"strategy":"object_method_unresolved","local":local,"method":method})
            return None
        else:
            local=raw
            imp=self.find_import(caller_file,local)
            if imp:
                target_files=self.resolve_import_target_files(imp)
                target_name=imp.get("imported") if imp.get("imported") not in {"default","*","module.exports"} else local
                for tf in target_files:
                    sig=self.find_signature(tf,target_name)
                    if sig:
                        self.resolution_report.append({"callerFile":caller_file,"call":raw,"strategy":"named_import_function","import":imp,"signature":sig})
                        return self.follow_reference(sig)
                    sig=self.find_exported_method(tf,target_name,imp)
                    if sig:
                        self.resolution_report.append({"callerFile":caller_file,"call":raw,"strategy":"commonjs_named_function","import":imp,"signature":sig})
                        return self.follow_reference(sig)
            sig=self.find_signature(caller_file,local)
            if sig:
                self.resolution_report.append({"callerFile":caller_file,"call":raw,"strategy":"same_file_function","signature":sig})
                return self.follow_reference(sig)
            self.resolution_report.append({"callerFile":caller_file,"call":raw,"strategy":"function_unresolved"})
            return None
    def follow_reference(self,sig):
        if not sig:
            return sig
        if sig.get("kind") in {"object_export_reference","object_method_reference"} and sig.get("targetName"):
            impl=self.find_signature(sig.get("file"),sig.get("targetName"))
            if impl and impl.get("params"):
                return impl
        if sig.get("kind")=="object_export_reference":
            impl=self.find_signature(sig.get("file"),sig.get("name"))
            if impl and impl.get("params"):
                return impl
        return sig
    def find_exported_method(self,file,method,imp=None):
        # method can be from module.exports object, exports.x, export default object, or service object method
        for ex in self.exports:
            if ex.get("file")!=file:
                continue
            if ex.get("exported") in {method,"module.exports"} or ex.get("local")==method:
                target=ex.get("local") if ex.get("local") else method
                sig=self.find_signature(file,target)
                if sig:
                    return sig
        # object literal qualifiedName service.method
        for s in self.signatures:
            if s.get("file")==file and (s.get("name")==method or s.get("qualifiedName","").endswith("."+method)):
                return s
        return None

    def find_import(self,file,local):
        for im in self.imports:
            if im.get("file")==file and im.get("local")==local:
                return im
        return None
    def resolve_import_target_files(self,imp):
        files=[]
        if imp.get("resolvedFile"):
            files.append(imp["resolvedFile"])
            # barrel / index.ts support: include re-export files from index
            for ex in self.exports:
                if ex.get("file")==imp["resolvedFile"] and ex.get("resolvedFile"):
                    files.append(ex["resolvedFile"])
        return list(dict.fromkeys(files))
    def find_signature(self,file,name):
        for s in self.signatures:
            if s.get("file")==file and (s.get("name")==name or s.get("qualifiedName","").endswith("."+name)):
                if s.get("kind") in {"object_export_reference","object_method_reference"}:
                    target=s.get("targetName") or name
                    impl=next((x for x in self.signatures if x.get("file")==file and x.get("name")==target and x.get("params")),None)
                    return impl or s
                return s
        for s in self.signatures:
            if s.get("file")==file and (s.get("name","").lower()==name.lower() or name.lower() in s.get("name","").lower()):
                return s
        return None
    def find_signature_any(self,file,name):
        return self.find_signature(file,name)


class TypeResolutionEngine:
    def __init__(self,validation_registry,type_registry):
        self.validation=validation_registry or {"schemas":[]}
        self.types=(type_registry or {}).get("types",[])
        self.report=[]
    def resolve_type_to_schema(self,type_name):
        original=type_name or ""
        normalized=self.clean_type(original)
        if not normalized:
            self.report.append({"type":original,"status":"empty"})
            return None
        direct=self.find_schema_by_name(normalized)
        if direct:
            self.report.append({"type":original,"normalized":normalized,"status":"resolved_direct","schema":direct.get("name"),"kind":direct.get("kind")})
            return direct
        wrapper=self.resolve_wrapper(original)
        if wrapper:
            self.report.append({"type":original,"normalized":normalized,"status":"resolved_wrapper","schema":wrapper.get("name"),"kind":wrapper.get("kind")})
            return wrapper
        self.report.append({"type":original,"normalized":normalized,"status":"unresolved"})
        return None
    def clean_type(self,t):
        t=str(t).strip()
        t=re.sub(r"^Promise<(.+)>$",r"\1",t)
        t=re.sub(r"^Partial<(.+)>$",r"\1",t)
        t=re.sub(r"^Required<(.+)>$",r"\1",t)
        t=re.sub(r"^Readonly<(.+)>$",r"\1",t)
        t=re.sub(r"^Array<(.+)>$",r"\1",t)
        t=t.replace("[]","")
        # remove union null/undefined
        t=t.split("|")[0].strip()
        return t.strip()
    def resolve_wrapper(self,t):
        raw=str(t).strip()
        # Pick<User, 'email' | 'name'>
        m=re.match(r"Pick<\s*([A-Za-z_$][\w$]*)\s*,\s*([^>]+)>",raw)
        if m:
            base=self.find_schema_by_name(m.group(1))
            if base:
                keys=re.findall(r"['\"]([^'\"]+)['\"]",m.group(2))
                return self.pick_schema(base,keys,"Pick")
        # Omit<User, 'password'>
        m=re.match(r"Omit<\s*([A-Za-z_$][\w$]*)\s*,\s*([^>]+)>",raw)
        if m:
            base=self.find_schema_by_name(m.group(1))
            if base:
                keys=re.findall(r"['\"]([^'\"]+)['\"]",m.group(2))
                return self.omit_schema(base,keys,"Omit")
        return None
    def pick_schema(self,base,keys,kind):
        b=json.loads(json.dumps(base))
        props=b.get("schema",{}).get("properties",{})
        req=b.get("schema",{}).get("required",[])
        b["name"]=kind+base.get("name","")
        b["schema"]["properties"]={k:v for k,v in props.items() if k in keys}
        b["schema"]["required"]=[k for k in req if k in keys]
        b["kind"]="typescript_utility_"+kind.lower()
        return b
    def omit_schema(self,base,keys,kind):
        b=json.loads(json.dumps(base))
        props=b.get("schema",{}).get("properties",{})
        req=b.get("schema",{}).get("required",[])
        b["name"]=kind+base.get("name","")
        b["schema"]["properties"]={k:v for k,v in props.items() if k not in keys}
        b["schema"]["required"]=[k for k in req if k not in keys]
        b["kind"]="typescript_utility_"+kind.lower()
        return b
    def find_schema_by_name(self,name):
        if not name: return None
        norm=re.sub(r"[^a-z0-9]","",str(name).lower())
        for s in self.validation.get("schemas",[]):
            sn=re.sub(r"[^a-z0-9]","",s.get("name","").lower())
            if sn==norm or sn.endswith(norm) or norm.endswith(sn):
                return s
        return None



class ObjectShapeAnalyzer:
    def __init__(self,cfg):
        self.cfg=cfg
        self.inf=TypeInferencer(cfg)
        self.report=[]
        self.shape_registry=[]
        self.propagation_report=[]
        self.merge_report=[]
        self.confidence_report=[]
        self.learning_patterns={}
    def analyze_body_context(self,body_info):
        raw=body_info.get("rawHandler","") if isinstance(body_info,dict) else ""
        aliases=set((body_info or {}).get("aliases",[]) or [])
        aliases.update(["body","request.body","req.body"])
        # Phase 1: collect local shape variables and builder functions
        local_shapes=self.collect_local_shape_variables(raw,aliases)
        builder_shapes=self.collect_builder_return_shapes(raw,aliases)
        # Phase 2: direct object shapes
        shapes=[]
        shapes += self.extract_variable_object_shapes(raw,aliases,local_shapes)
        shapes += self.extract_inline_call_object_shapes(raw,aliases,local_shapes,builder_shapes)
        shapes += self.extract_object_assign_shapes(raw,aliases,local_shapes)
        shapes += self.extract_spread_shapes(raw,aliases,local_shapes)
        shapes += self.extract_builder_call_shapes(raw,aliases,builder_shapes)
        # Phase 3: normalize + confidence
        normalized=[]
        for sh in shapes:
            sh=self.expand_shape_spreads(sh,local_shapes)
            sh["confidence"]=self.confidence_for(sh)
            sh["shapeId"]="shape-"+sha(json.dumps(sh,sort_keys=True))[:12]
            normalized.append(sh)
            self.shape_registry.append(sh)
            self.confidence_report.append({"shapeId":sh["shapeId"],"source":sh.get("source"),"confidence":sh["confidence"],"fieldCount":len(sh.get("fields",[]))})
            self.learn_pattern(sh)
        self.report.append({"bodyAliases":sorted([a for a in aliases if a]),"localShapes":list(local_shapes.keys()),"builderShapes":list(builder_shapes.keys()),"shapesFound":len(normalized),"shapes":normalized})
        return normalized
    def schema_from_shapes(self,shapes):
        props={}; required=[]
        for sh in shapes:
            for f in sh.get("fields",[]):
                name=f.get("name")
                if not name or name.startswith("__"):
                    continue
                if name not in props:
                    schema=self.inf.infer(name,f.get("raw",""))
                    schema["x-qaira-source"]=sh.get("source","object_shape")
                    schema["x-qaira-shape-confidence"]=sh.get("confidence",0.75)
                    if f.get("fromBody"): schema["x-qaira-from-body"]=True
                    props[name]=schema
                if f.get("required",False): required.append(name)
        if not props:
            return {}
        return {"type":"object","required":sorted(set(required)),"properties":props}
    def collect_local_shape_variables(self,raw,aliases):
        shapes={}
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\{([\s\S]{0,4000}?)\}\s*;?",raw):
            var=m.group(1); body=m.group(2)
            fields=self.fields_from_object_body(body,aliases)
            spreads=self.spreads_from_object_body(body)
            if fields or spreads:
                shapes[var]={"name":var,"source":"variable_object_literal","fields":fields,"spreads":spreads,"raw":body[:800]}
        # const payload = Object.assign(...)
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*Object\.assign\s*\(([\s\S]{0,3000}?)\)",raw):
            var=m.group(1); args=m.group(2)
            fields=[]
            spreads=[]
            for obj in re.finditer(r"\{([\s\S]{0,1200}?)\}",args):
                fields += self.fields_from_object_body(obj.group(1),aliases)
                spreads += self.spreads_from_object_body(obj.group(1))
            for a in aliases:
                if a and re.search(r"\b"+re.escape(a)+r"\b",args):
                    spreads.append(a)
            shapes[var]={"name":var,"source":"object_assign_variable","fields":fields,"spreads":spreads,"raw":args[:800]}
        return shapes
    def collect_builder_return_shapes(self,raw,aliases):
        builders={}
        # function buildPayload(body) { return { ... } }
        for m in re.finditer(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{([\s\S]{0,8000}?)\n?\}",raw):
            name=m.group(1); params=m.group(2); body=m.group(3)
            for ret in re.finditer(r"return\s+\{([\s\S]{0,4000}?)\}",body):
                fields=self.fields_from_object_body(ret.group(1),aliases | set([p.strip().split(':')[0].strip() for p in params.split(',') if p.strip()]))
                spreads=self.spreads_from_object_body(ret.group(1))
                builders[name]={"name":name,"source":"builder_function_return","fields":fields,"spreads":spreads,"params":params,"raw":ret.group(1)[:1000]}
        # const buildPayload = (body) => ({ ... }) or => { return { ... } }
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*(?:\(?\s*\{([\s\S]{0,4000}?)\}\s*\)?|\{([\s\S]{0,6000}?)\})",raw):
            name=m.group(1); params=m.group(2); inline_obj=m.group(3) or ""
            block=m.group(4) or ""
            body=inline_obj
            if block:
                ret=re.search(r"return\s+\{([\s\S]{0,4000}?)\}",block)
                body=ret.group(1) if ret else ""
            if body:
                param_aliases=aliases | set([p.strip().split(':')[0].strip() for p in params.split(',') if p.strip()])
                fields=self.fields_from_object_body(body,param_aliases)
                spreads=self.spreads_from_object_body(body)
                if fields or spreads:
                    builders[name]={"name":name,"source":"builder_arrow_return","fields":fields,"spreads":spreads,"params":params,"raw":body[:1000]}
        # const buildPayload = function(body) { return { ... } }
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function\s*\(([^)]*)\)\s*\{([\s\S]{0,8000}?)\}",raw):
            name=m.group(1); params=m.group(2); body=m.group(3)
            ret=re.search(r"return\s+\{([\s\S]{0,4000}?)\}",body)
            if ret:
                param_aliases=aliases | set([p.strip().split(':')[0].strip() for p in params.split(',') if p.strip()])
                fields=self.fields_from_object_body(ret.group(1),param_aliases)
                spreads=self.spreads_from_object_body(ret.group(1))
                builders[name]={"name":name,"source":"builder_function_expression_return","fields":fields,"spreads":spreads,"params":params,"raw":ret.group(1)[:1000]}
        return builders

    def extract_variable_object_shapes(self,raw,aliases,local_shapes):
        out=[]
        for name,shape in local_shapes.items():
            sh=dict(shape)
            sh["source"]="variable_object_literal"
            out.append(sh)
        return out
    def extract_inline_call_object_shapes(self,raw,aliases,local_shapes,builder_shapes):
        out=[]
        for m in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(\s*\{([\s\S]{0,3000}?)\}\s*\)",raw):
            call=m.group(1); body=m.group(2)
            fields=self.fields_from_object_body(body,aliases)
            spreads=self.spreads_from_object_body(body)
            if fields or spreads:
                out.append({"name":call,"source":"inline_service_call_object_literal","call":call,"fields":fields,"spreads":spreads,"raw":body[:800]})
        # service.create(payload) -> use known payload variable shape
        for m in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(\s*([A-Za-z_$][\w$]*)\s*\)",raw):
            call=m.group(1); arg=m.group(2)
            if arg in local_shapes:
                sh=dict(local_shapes[arg]); sh["source"]="service_call_variable_shape"; sh["call"]=call; sh["name"]=arg
                out.append(sh)
            elif arg in builder_shapes:
                sh=dict(builder_shapes[arg]); sh["source"]="service_call_builder_shape"; sh["call"]=call; sh["name"]=arg
                out.append(sh)
        return out
    def extract_object_assign_shapes(self,raw,aliases,local_shapes):
        out=[]
        for m in re.finditer(r"Object\.assign\s*\(([\s\S]{0,3000}?)\)",raw):
            args=m.group(1)
            fields=[]; spreads=[]
            for obj in re.finditer(r"\{([\s\S]{0,1200}?)\}",args):
                fields += self.fields_from_object_body(obj.group(1),aliases)
                spreads += self.spreads_from_object_body(obj.group(1))
            for a in aliases:
                if a and re.search(r"\b"+re.escape(a)+r"\b",args):
                    spreads.append(a)
            for v in local_shapes.keys():
                if re.search(r"\b"+re.escape(v)+r"\b",args):
                    spreads.append(v)
            if fields or spreads:
                out.append({"name":"Object.assign","source":"object_assign","fields":fields,"spreads":spreads,"raw":args[:800]})
        return out
    def extract_spread_shapes(self,raw,aliases,local_shapes):
        out=[]
        for m in re.finditer(r"\{([\s\S]{0,2500}?)\}",raw):
            body=m.group(1)
            spreads=self.spreads_from_object_body(body)
            if not spreads:
                continue
            fields=self.fields_from_object_body(body,aliases)
            out.append({"name":"spread_object","source":"spread_body_object","fields":fields,"spreads":spreads,"raw":body[:800]})
        return out
    def extract_builder_call_shapes(self,raw,aliases,builder_shapes):
        out=[]
        builder_vars={}
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)",raw):
            var=m.group(1); builder=m.group(2); args=m.group(3)
            if builder in builder_shapes:
                sh=dict(builder_shapes[builder]); sh["name"]=var; sh["source"]="builder_call_variable_shape"; sh["builder"]=builder; sh["builderArgs"]=args
                builder_vars[var]=sh
                out.append(sh)
                self.propagation_report.append({"from":builder,"to":var,"type":"builder_return_to_variable","fields":len(sh.get("fields",[]))})
        # service.create(payload) where payload came from builder
        for m in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(\s*([A-Za-z_$][\w$]*)\s*\)",raw):
            call=m.group(1); arg=m.group(2)
            if arg in builder_vars:
                sh=dict(builder_vars[arg]); sh["source"]="service_call_builder_propagated_shape"; sh["call"]=call; sh["name"]=arg
                out.append(sh)
                self.propagation_report.append({"from":arg,"to":call,"type":"builder_variable_to_service_call","fields":len(sh.get("fields",[]))})
        return out

    def spreads_from_object_body(self,body):
        spreads=[]
        for sm in re.finditer(r"\.\.\.\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)",body):
            spreads.append(sm.group(1))
        return spreads
    def expand_shape_spreads(self,shape,local_shapes):
        fields=list(shape.get("fields",[]))
        expanded=[]
        for sp in shape.get("spreads",[]) or []:
            if sp in local_shapes:
                fields += local_shapes[sp].get("fields",[])
                expanded.append(sp)
                self.merge_report.append({"target":shape.get("name"),"spread":sp,"status":"expanded","fields":len(local_shapes[sp].get("fields",[]))})
            elif sp in {"body","request.body","req.body"} or sp.endswith(".body"):
                self.merge_report.append({"target":shape.get("name"),"spread":sp,"status":"body_spread_detected_fields_unknown"})
            else:
                self.merge_report.append({"target":shape.get("name"),"spread":sp,"status":"spread_unresolved"})
        shape["fields"]=self.unique_fields(fields)
        shape["expandedSpreads"]=expanded
        if expanded:
            self.propagation_report.append({"shape":shape.get("name"),"expandedSpreads":expanded,"fieldCount":len(shape["fields"])})
        return shape
    def fields_from_object_body(self,body,aliases):
        fields=[]
        for fm in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([^,\n}]+)",body):
            key=fm.group(1); val=fm.group(2).strip()
            if key in {"http","https"}:
                continue
            from_body=bool(re.search(r"(?:request|req)\.body\."+re.escape(key)+r"\b",val))
            for a in aliases:
                if a and "." not in a:
                    from_body = from_body or bool(re.search(r"\b"+re.escape(a)+r"\."+re.escape(key)+r"\b",val))
            fields.append({"name":key,"raw":val,"fromBody":from_body,"required":False})
        for token in re.split(r",|\n",body):
            s=token.strip()
            if not re.match(r"^[A-Za-z_$][\w$]*$",s):
                continue
            if s in {"return","await","async","true","false","null","undefined"}:
                continue
            fields.append({"name":s,"raw":s,"fromBody":s in aliases,"required":False})
        return self.unique_fields(fields)
    def unique_fields(self,fields):
        unique=[]; seen=set()
        for f in fields:
            name=f.get("name")
            if name and name not in seen:
                seen.add(name); unique.append(f)
        return unique
    def confidence_for(self,shape):
        src=shape.get("source","")
        if src=="inline_service_call_object_literal": return 0.98
        if src=="service_call_variable_shape": return 0.95
        if src=="variable_object_literal": return 0.94
        if src=="object_assign": return 0.90
        if src=="spread_body_object": return 0.88
        if src in {"builder_function_return","builder_arrow_return","builder_call_variable_shape","service_call_builder_shape"}: return 0.86
        return 0.80
    def learn_pattern(self,shape):
        key=shape.get("source","unknown")
        item=self.learning_patterns.setdefault(key,{"pattern":key,"successCount":0,"totalConfidence":0.0})
        item["successCount"]+=1
        item["totalConfidence"]+=float(shape.get("confidence",0))
        item["avgConfidence"]=round(item["totalConfidence"]/item["successCount"],4)

class SchemaEnricher:
    def __init__(self,cfg,validation_registry,signature_registry=None,import_registry=None):
        self.cfg=cfg
        self.validation=validation_registry or {"schemas":[]}
        self.signatures=(signature_registry or {}).get("signatures",[])
        self.import_registry=import_registry or {"imports":[],"exports":[]}
        self.service_resolver=ServiceCallResolver(signature_registry,self.import_registry)
        self.type_engine=TypeResolutionEngine(validation_registry,(validation_registry or {}).get("typeRegistry",{}))
        self.object_shape_analyzer=ObjectShapeAnalyzer(cfg)
        self.inf=TypeInferencer(cfg)
        self.dto_trace=[]
    def enrich_trace(self,route,trace):
        schema=trace.get("schema") or {}
        resolution={"route":route.get("path"),"method":route.get("method"),"strategy":"none","confidence":trace.get("confidence",0)}
        fields=(schema.get("properties") or {})
        body_info={}
        for item in trace.get("trace",[]):
            if isinstance(item,dict) and item.get("type") in {"inline_handler_body_analysis","regex_inline_body_analysis"}:
                body_info=item.get("bodyInfo") or {}
        # 1 named schema refs
        for ref in body_info.get("schemaRefs",[]) if isinstance(body_info,dict) else []:
            match=self.find_schema_by_name(ref)
            if match:
                resolution={"route":route.get("path"),"method":route.get("method"),"strategy":"named_schema_reference","schema":match["name"],"kind":match["kind"],"confidence":0.94}
                self.dto_trace.append({"route":route.get("path"),"resolution":resolution,"bodyInfo":body_info})
                return self.merge_with_observed_fields(match["schema"],body_info),resolution
        # 2 import-aware service call signature DTO trace
        sig_result=self.resolve_from_service_call_signature(route,body_info)
        if sig_result:
            match,resolution=sig_result
            self.dto_trace.append({"route":route.get("path"),"resolution":resolution,"bodyInfo":body_info})
            return self.merge_with_observed_fields(match["schema"],body_info),resolution
        # 3 route/service candidate schema if current schema has unknown fields
        if schema and not fields:
            for cand in self.route_schema_candidates(route.get("path",""),body_info):
                match=self.find_schema_by_name(cand)
                if match:
                    resolution={"route":route.get("path"),"method":route.get("method"),"strategy":"route_or_service_name_schema","schema":match["name"],"kind":match["kind"],"candidate":cand,"confidence":0.86}
                    self.dto_trace.append({"route":route.get("path"),"resolution":resolution,"bodyInfo":body_info})
                    return self.merge_with_observed_fields(match["schema"],body_info),resolution
        # 4 object shape analyzer: object literals passed to services or payload vars
        shapes=self.object_shape_analyzer.analyze_body_context(body_info)
        object_schema=self.object_shape_analyzer.schema_from_shapes(shapes)
        if object_schema and object_schema.get("properties"):
            if schema and fields:
                object_schema=self.merge_two_schemas(schema,object_schema)
            resolution={"route":route.get("path"),"method":route.get("method"),"strategy":"object_shape_analyzer","confidence":0.9,"fields":len(object_schema.get("properties",{}))}
            self.dto_trace.append({"route":route.get("path"),"resolution":resolution,"bodyInfo":body_info,"objectShapes":shapes})
            return object_schema,resolution

        # 5 enrich existing V32 fields
        if fields:
            enriched=json.loads(json.dumps(schema))
            for k,v in enriched.get("properties",{}).items():
                inferred=self.inf.infer(k,json.dumps(v))
                inferred.update(v)
                enriched["properties"][k]=inferred
            resolution={"route":route.get("path"),"method":route.get("method"),"strategy":"v32_body_fields_type_enriched","confidence":max(trace.get("confidence",0.8),0.82),"fields":len(fields)}
            self.dto_trace.append({"route":route.get("path"),"resolution":resolution,"bodyInfo":body_info})
            return enriched,resolution
        resolution={"route":route.get("path"),"method":route.get("method"),"strategy":"unresolved","confidence":trace.get("confidence",0)}
        self.dto_trace.append({"route":route.get("path"),"resolution":resolution,"bodyInfo":body_info})
        return schema,resolution
    def resolve_from_service_call_signature(self,route,body_info):
        if not isinstance(body_info,dict): return None
        aliases=set(body_info.get("aliases",[]) or [])
        aliases.update(["request.body","req.body","body"])
        for sc in body_info.get("serviceCalls",[]) or []:
            call=sc.get("call","")
            args=sc.get("args","")
            arg_list=[a.strip() for a in args.split(",") if a.strip()]
            for idx,arg in enumerate(arg_list):
                is_body_arg = arg in aliases or any(a and re.search(r"\b"+re.escape(a)+r"\b",arg) for a in aliases if a not in {"request.body","req.body"})
                if not is_body_arg:
                    continue
                sig=self.service_resolver.resolve(route.get("file"),call)
                if sig and idx < len(sig.get("params",[])):
                    ptype=sig["params"][idx].get("type","")
                    match=self.type_engine.resolve_type_to_schema(ptype) or self.find_schema_by_name(ptype)
                    if match:
                        return match,{"route":route.get("path"),"method":route.get("method"),"strategy":"type_resolved_import_aware_signature_dto_trace","call":call,"signatureFile":sig.get("file"),"signatureLine":sig.get("line"),"param":sig["params"][idx],"schema":match["name"],"kind":match["kind"],"confidence":0.97}
        return None
    def merge_two_schemas(self,a,b):
        merged=json.loads(json.dumps(a or {"type":"object","properties":{},"required":[]}))
        merged.setdefault("type","object")
        merged.setdefault("properties",{})
        merged.setdefault("required",[])
        for k,v in (b or {}).get("properties",{}).items():
            if k not in merged["properties"]:
                merged["properties"][k]=v
        merged["required"]=sorted(set((merged.get("required") or []) + ((b or {}).get("required") or [])))
        return merged

    def merge_with_observed_fields(self,schema,body_info):
        if not isinstance(schema,dict):
            return schema
        merged=json.loads(json.dumps(schema))
        merged.setdefault("properties",{})
        merged.setdefault("required",[])
        observed=[]
        if isinstance(body_info,dict):
            observed += body_info.get("fields",[]) or []
            observed += body_info.get("destructuredFields",[]) or []
        for f in sorted(set(observed)):
            if f not in merged["properties"]:
                inferred=self.inf.infer(f,f)
                inferred["x-qaira-source"]="observed_body_field_merged"
                merged["properties"][f]=inferred
        return merged

    def route_schema_candidates(self,path,body_info):
        tokens=[x for x in re.split(r"[^A-Za-z0-9]+",path) if x]
        bases=[]
        for t in tokens:
            bases.append(t[:1].upper()+t[1:])
        for sc in body_info.get("serviceCalls",[]) if isinstance(body_info,dict) else []:
            method=sc.get("call","").split(".")[-1]
            if method: bases.append(method[:1].upper()+method[1:])
        candidates=[]
        for b in bases:
            for suffix in ["Schema","Dto","DTO","Request","Input","Body","Payload"]:
                candidates.append(b+suffix)
                candidates.append("Create"+b+suffix)
                candidates.append("Update"+b+suffix)
        return candidates
    def find_schema_by_name(self,name):
        if not name: return None
        clean=str(name)
        # strip common wrappers
        clean=re.sub(r"Promise<(.+)>",r"\1",clean)
        clean=re.sub(r"Partial<(.+)>",r"\1",clean)
        clean=re.sub(r"Required<(.+)>",r"\1",clean)
        clean=re.sub(r"Readonly<(.+)>",r"\1",clean)
        clean=clean.replace("[]","").replace(">","").strip()
        norm=re.sub(r"[^a-z0-9]","",clean.lower())
        for s in self.validation.get("schemas",[]):
            sn=re.sub(r"[^a-z0-9]","",s.get("name","").lower())
            if sn==norm or sn.endswith(norm) or norm.endswith(sn):
                return s
        return None

class InlineHandlerCompiler:
    def run(self,fs,cfg):
        routes=[]; nodes=[]; edges=[]; req_traces=[]; res_traces=[]; handler_report=[]; body_report=[]; parser_report={"treeSitterAvailable":TREE_SITTER_AVAILABLE,"files":[],"errors":[]}
        for p in fs.all_files():
            if p.suffix.lower() not in {".js",".jsx",".ts",".tsx"}: continue
            r=fs.rel(p); t=fs.read(p)
            try:
                if TREE_SITTER_AVAILABLE and cfg["parsing"].get("prefer_tree_sitter",True):
                    fr=self.parse_file_ts(t,r)
                    parser_report["files"].append({"file":r,"parser":"tree-sitter"})
                else:
                    fr=self.parse_file_regex(t,r)
                    parser_report["files"].append({"file":r,"parser":"regex"})
            except Exception as e:
                parser_report["errors"].append({"file":r,"error":str(e)})
                fr=self.parse_file_regex(t,r)
                parser_report["files"].append({"file":r,"parser":"regex-fallback"})
            routes += fr["routes"]; nodes += fr["nodes"]; edges += fr["edges"]; req_traces += fr["requestTraces"]; res_traces += fr["responseTraces"]; handler_report += fr["handlerReport"]; body_report += fr["bodyReport"]
        graph={"nodes":nodes,"edges":edges}
        return routes,graph,req_traces,res_traces,handler_report,body_report,parser_report
    def ts_language(self,ext):
        return Language(tsjavascript.language()) if ext in {".js",".jsx"} else Language(tstypescript.language_typescript())
    def set_lang(self,parser,lang):
        if hasattr(parser,"set_language"): parser.set_language(lang)
        else: parser.language=lang
    def child(self,n,name):
        try: return n.child_by_field_name(name)
        except Exception: return None
    def walk(self,n):
        yield n
        for c in getattr(n,"children",[]) or []:
            yield from self.walk(c)
    def parse_file_ts(self,t,r):
        src=t.encode("utf-8"); parser=Parser(); self.set_lang(parser,self.ts_language(Path(r).suffix.lower()))
        tree=parser.parse(src)
        routes=[]; nodes=[node("file:"+r,"File",{"file":r})]; edges=[]; req_traces=[]; res_traces=[]; handler_report=[]; body_report=[]
        for n in self.walk(tree.root_node):
            if n.type!="call_expression": continue
            f=self.child(n,"function")
            if not f: continue
            raw_fn=text_of(src,f)
            m=re.match(r"(?:app|router|server|fastify)\.(get|post|put|patch|delete)$",raw_fn,re.I)
            if not m: continue
            args=[c for c in n.children if c.type=="arguments"]
            if not args: continue
            arg_nodes=[c for c in args[0].children if c.type not in {"(",")",","}]
            if not arg_nodes: continue
            path_node=arg_nodes[0]
            if path_node.type not in {"string","template_string"}: continue
            method=m.group(1).upper(); path=norm_path(text_of(src,path_node).strip("'\"`"))
            handler_node=None; schema_node=None
            # Fastify may be: fastify.post(path, opts, async handler)
            for a in arg_nodes[1:]:
                if a.type in {"arrow_function","function_expression"}:
                    handler_node=a
                elif a.type=="identifier":
                    pass
                elif a.type=="object":
                    # options object can contain schema + handler
                    schema_node=a
                    for inner in self.walk(a):
                        if inner.type in {"arrow_function","function_expression"}:
                            handler_node=inner
            rid=f"route:{method}:{path}:{r}:{node_line(n)}"
            route={"id":rid,"method":method,"path":path,"file":r,"line":node_line(n),"handler":"<inline>" if handler_node else "<external>","parser":"tree-sitter","inline":bool(handler_node)}
            routes.append(route); nodes.append(node(rid,"Route",route)); edges.append(edge("file:"+r,rid,"DECLARES_ROUTE"))
            handler_report.append({"route":path,"method":method,"file":r,"inlineHandlerDetected":bool(handler_node),"line":node_line(n)})
            req_schema={}; req_trace=[{"type":"route","route":route}]; res_trace=[{"type":"route","route":route}]
            if schema_node:
                schema_fields=self.extract_fastify_schema_fields(schema_node,src)
                if schema_fields:
                    req_schema=self.schema_from_fields(schema_fields,"fastify_schema")
                    req_trace.append({"type":"fastify_schema_body","fields":schema_fields})
            if handler_node:
                hid=f"inline_handler:{method}:{path}:{r}:{node_line(handler_node)}"
                nodes.append(node(hid,"InlineHandler",{"file":r,"line":node_line(handler_node),"route":path}))
                edges.append(edge(rid,hid,"HANDLED_BY",{"confidence":0.99,"mode":"inline"}))
                body_info=self.extract_body_info(handler_node,src)
                body_report.append({"route":path,"method":method,"file":r,**body_info})
                req_trace.append({"type":"inline_handler_body_analysis","bodyInfo":body_info})
                if not req_schema:
                    req_schema=self.schema_from_body_info(body_info)
                res_info=self.extract_response_info(handler_node,src,body_info)
                res_trace.append({"type":"inline_response_analysis","responseInfo":res_info})
            req_traces.append({"routeId":rid,"method":method,"path":path,"schema":req_schema,"trace":req_trace,"confidence":0.9 if req_schema else 0.25})
            res_traces.append({"routeId":rid,"method":method,"path":path,"schema":self.response_schema_from_trace(res_trace),"trace":res_trace,"confidence":0.6})
        return {"routes":routes,"nodes":nodes,"edges":edges,"requestTraces":req_traces,"responseTraces":res_traces,"handlerReport":handler_report,"bodyReport":body_report}
    def extract_fastify_schema_fields(self,schema_node,src):
        raw=text_of(src,schema_node)
        fields=[]
        m=re.search(r"body\s*:\s*\{([\s\S]{0,3000}?)\}\s*(?:,|\})",raw)
        if m:
            body=m.group(1)
            props=re.search(r"properties\s*:\s*\{([\s\S]{0,2000}?)\}",body)
            if props:
                for fm in re.finditer(r"([A-Za-z_$][\w$]*)\s*:",props.group(1)):
                    fields.append(fm.group(1))
            req=re.search(r"required\s*:\s*\[([^\]]*)\]",body)
            required=[x.strip().strip("'\"`") for x in req.group(1).split(",")] if req else []
            return [{"name":f,"required":f in required,"source":"fastify_schema"} for f in sorted(set(fields))]
        return []
    def extract_body_info(self,handler,src):
        raw=text_of(src,handler)
        aliases=[]; fields=[]; destructured=[]; params=[]; query=[]
        # aliases: const body = request.body
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:request|req)\.body",raw):
            aliases.append(m.group(1))
        # destructuring: const { a, b } = request.body
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:request|req)\.body",raw):
            for part in m.group(1).split(","):
                name=part.strip().split(":")[0].strip()
                if name and re.match(r"^[A-Za-z_$][\w$]*$",name): destructured.append(name); fields.append(name)
        # direct usage: request.body.email / body.email
        for m in re.finditer(r"(?:request|req)\.body\.([A-Za-z_$][\w$]*)",raw):
            fields.append(m.group(1))
        for alias in aliases:
            for m in re.finditer(r"\b"+re.escape(alias)+r"\.([A-Za-z_$][\w$]*)",raw):
                fields.append(m.group(1))
        for m in re.finditer(r"(?:request|req)\.params\.([A-Za-z_$][\w$]*)",raw):
            params.append(m.group(1))
        for m in re.finditer(r"(?:request|req)\.query\.([A-Za-z_$][\w$]*)",raw):
            query.append(m.group(1))
        # Fastify common: const { body } = request then body.email
        if re.search(r"\{\s*body\s*\}\s*=\s*(?:request|req)",raw) and "body" not in aliases:
            aliases.append("body")
            for m in re.finditer(r"\bbody\.([A-Za-z_$][\w$]*)",raw):
                fields.append(m.group(1))
        has_body=bool(re.search(r"(?:request|req)\.body|\bbody\b",raw))
        service_calls=[]
        schema_refs=[]
        for alias in set(aliases+["body"]):
            if alias:
                for sm in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(([^)]*\b"+re.escape(alias)+r"\b[^)]*)\)",raw):
                    service_calls.append({"call":sm.group(1),"args":sm.group(2)})
        for sm in re.finditer(r"(?:schema|body|validation|validator)\s*:\s*([A-Za-z_$][\w$]*)",raw):
            schema_refs.append(sm.group(1))
        return {"hasBody":has_body,"aliases":sorted(set(aliases)),"fields":sorted(set(fields)),"destructuredFields":sorted(set(destructured)),"params":sorted(set(params)),"query":sorted(set(query)),"serviceCalls":service_calls,"schemaRefs":sorted(set(schema_refs)),"rawHandler":raw}
    def schema_from_fields(self,fields,source):
        props={}; req=[]
        for f in fields:
            name=f["name"] if isinstance(f,dict) else str(f)
            props[name]={"type":"string","x-qaira-source":source}
            if isinstance(f,dict) and f.get("required"): req.append(name)
        return {"type":"object","required":sorted(set(req)),"properties":props} if props else {}
    def schema_from_body_info(self,info):
        if not info.get("fields"):
            if info.get("hasBody"):
                return {"type":"object","required":[],"properties":{},"x-qaira-note":"body detected but fields unresolved"}
            return {}
        return {"type":"object","required":[],"properties":{f:{"type":"string","x-qaira-source":"inline_handler_body"} for f in info.get("fields",[])}}
    def extract_response_info(self,handler,src,body_info):
        raw=text_of(src,handler)
        sends=[]
        for m in re.finditer(r"(?:reply|res|response)\.(?:send|json)\s*\(([\s\S]{0,800}?)\)",raw):
            sends.append(m.group(1).strip())
        for m in re.finditer(r"return\s+([\s\S]{0,800}?);",raw):
            sends.append(m.group(1).strip())
        return {"sendExpressions":sends[:20]}
    def response_schema_from_trace(self,res_trace):
        props={}
        for item in res_trace:
            if item.get("type")=="inline_response_analysis":
                for expr in item.get("responseInfo",{}).get("sendExpressions",[]):
                    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:",expr):
                        key=m.group(1)
                        if key not in {"http","https"}: props[key]={"type":"string","x-qaira-source":"inline_response_object"}
                    if re.search(r"\bid\b",expr) and "id" not in props:
                        props["id"]={"type":"string","x-qaira-source":"inline_response_expression"}
        return {"type":"object","properties":props} if props else {"type":"object","properties":{"id":{"type":"string","x-qaira-source":"fallback_minimal"}}}
    def parse_file_regex(self,t,r):
        routes=[]; nodes=[node("file:"+r,"File",{"file":r,"parser":"regex"})]; edges=[]; req_traces=[]; res_traces=[]; handler_report=[]; body_report=[]
        route_pat=r"(?:app|router|server|fastify)\.(get|post|put|patch|delete)\s*\(\s*[`'\"]([^`'\"]+)[`'\"]\s*,(?P<rest>[\s\S]{0,5000}?)\)\s*;?"
        for m in re.finditer(route_pat,t,re.I):
            method=m.group(1).upper(); path=norm_path(m.group(2)); rest=m.group("rest")
            rid=f"route:{method}:{path}:{r}:{line_no(t,m.start())}"
            route={"id":rid,"method":method,"path":path,"file":r,"line":line_no(t,m.start()),"handler":"<inline-regex>","parser":"regex","inline":True}
            info=self.extract_body_info_from_text(rest)
            req_schema=self.schema_from_body_info(info)
            routes.append(route); nodes.append(node(rid,"Route",route)); edges.append(edge("file:"+r,rid,"DECLARES_ROUTE"))
            handler_report.append({"route":path,"method":method,"file":r,"inlineHandlerDetected":True,"line":line_no(t,m.start()),"parser":"regex"})
            body_report.append({"route":path,"method":method,"file":r,**info})
            req_traces.append({"routeId":rid,"method":method,"path":path,"schema":req_schema,"trace":[{"type":"regex_inline_body_analysis","bodyInfo":info}],"confidence":0.7 if req_schema else 0.2})
            res_traces.append({"routeId":rid,"method":method,"path":path,"schema":{"type":"object","properties":{"id":{"type":"string","x-qaira-source":"fallback_minimal"}}},"trace":[],"confidence":0.3})
        return {"routes":routes,"nodes":nodes,"edges":edges,"requestTraces":req_traces,"responseTraces":res_traces,"handlerReport":handler_report,"bodyReport":body_report}
    def extract_body_info_from_text(self,raw):
        aliases=[]; fields=[]; destructured=[]
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:request|req)\.body",raw):
            aliases.append(m.group(1))
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:request|req)\.body",raw):
            for part in m.group(1).split(","):
                name=part.strip().split(":")[0].strip()
                if re.match(r"^[A-Za-z_$][\w$]*$",name): destructured.append(name); fields.append(name)
        for m in re.finditer(r"(?:request|req)\.body\.([A-Za-z_$][\w$]*)",raw):
            fields.append(m.group(1))
        for alias in aliases:
            for m in re.finditer(r"\b"+re.escape(alias)+r"\.([A-Za-z_$][\w$]*)",raw):
                fields.append(m.group(1))
        if re.search(r"\{\s*body\s*\}\s*=\s*(?:request|req)",raw):
            aliases.append("body")
            for m in re.finditer(r"\bbody\.([A-Za-z_$][\w$]*)",raw):
                fields.append(m.group(1))
        service_calls=[]
        for alias in set(aliases+["body"]):
            if alias:
                for sm in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(([^)]*\b"+re.escape(alias)+r"\b[^)]*)\)",raw):
                    service_calls.append({"call":sm.group(1),"args":sm.group(2)})
        return {"hasBody":bool(re.search(r"(?:request|req)\.body|\bbody\b",raw)),"aliases":sorted(set(aliases)),"fields":sorted(set(fields)),"destructuredFields":sorted(set(destructured)),"params":[],"query":[],"serviceCalls":service_calls,"schemaRefs":[],"rawHandler":raw}

class AuthScopeCompiler:
    def run(self,fs,routes):
        effective={}
        for rt in routes:
            required=not any(x in rt["path"].lower() for x in ["login","signup","register","health"])
            effective[rt["id"]]={"route":rt["path"],"required":required,"type":"bearer" if required else "none","confidence":0.65}
        return {"nodes":[],"edges":[]},effective


class RequestContextEngine:
    def __init__(self,cfg):
        self.cfg=cfg
        self.inf=TypeInferencer(cfg)
        self.report=[]
    def analyze_trace(self,route,trace):
        raw=""
        body_info={}
        for item in trace.get("trace",[]):
            if isinstance(item,dict) and item.get("type") in {"inline_handler_body_analysis","regex_inline_body_analysis"}:
                body_info=item.get("bodyInfo") or {}
                raw=body_info.get("rawHandler","")
        contexts={
            "body": self.body_fields(body_info, raw),
            "query": self.query_fields(body_info, raw),
            "path": self.path_fields(route, body_info, raw),
            "header": self.header_fields(raw),
            "cookie": self.cookie_fields(raw)
        }
        # enforce method awareness
        if route.get("method") in {"GET","HEAD","OPTIONS"}:
            contexts["body"]=[]
        result={
            "routeId":route.get("id"),
            "method":route.get("method"),
            "path":route.get("path"),
            "contexts":contexts,
            "counts":{k:len(v) for k,v in contexts.items()}
        }
        self.report.append(result)
        return result
    def field_obj(self,name,raw="",source="request_context",required=False):
        sch=self.inf.infer(name,raw)
        return {"name":name,"schema":sch,"raw":raw,"source":source,"required":required,"confidence":self.confidence_for_source(source)}
    def confidence_for_source(self,source):
        if source in {"path_template","body_direct","query_direct","path_direct","header_direct","cookie_direct"}: return 0.98
        if source.endswith("_bracket") or source.endswith("_function"): return 0.96
        if source.endswith("_destructured"): return 0.94
        if "body_info" in source: return 0.90
        return 0.85

    def body_fields(self,body_info,raw):
        out=[]
        for f in (body_info.get("fields",[]) if isinstance(body_info,dict) else []):
            out.append(self.field_obj(f,f,"body_info"))
        for f in (body_info.get("destructuredFields",[]) if isinstance(body_info,dict) else []):
            out.append(self.field_obj(f,f,"body_destructured"))
        # direct request.body.foo
        for m in re.finditer(r"(?:request|req)\.body\.([A-Za-z_$][\w$]*)",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"body_direct"))
        return self.unique(out)
    def query_fields(self,body_info,raw):
        out=[]
        for f in (body_info.get("query",[]) if isinstance(body_info,dict) else []):
            out.append(self.field_obj(f,f,"query_body_info"))
        for m in re.finditer(r"(?:request|req)\.query\.([A-Za-z_$][\w$]*)",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"query_direct"))
        for m in re.finditer(r"(?:request|req)\.query\s*\[\s*['\"]([^'\"]+)['\"]\s*\]",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"query_bracket"))
        # destructuring const { page, limit } = request.query
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:request|req)\.query",raw):
            for part in m.group(1).split(","):
                name=part.strip().split(":")[0].strip()
                if re.match(r"^[A-Za-z_$][\w$]*$",name):
                    out.append(self.field_obj(name,name,"query_destructured"))
        return self.unique(out)
    def path_fields(self,route,body_info,raw):
        out=[]
        # from route template
        for m in re.finditer(r"\{([^}]+)\}",route.get("path","")):
            out.append(self.field_obj(m.group(1),m.group(0),"path_template",True))
        for f in (body_info.get("params",[]) if isinstance(body_info,dict) else []):
            out.append(self.field_obj(f,f,"path_body_info",True))
        for m in re.finditer(r"(?:request|req)\.params\.([A-Za-z_$][\w$]*)",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"path_direct",True))
        for m in re.finditer(r"(?:request|req)\.params\s*\[\s*['\"]([^'\"]+)['\"]\s*\]",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"path_bracket",True))
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:request|req)\.params",raw):
            for part in m.group(1).split(","):
                name=part.strip().split(":")[0].strip()
                if re.match(r"^[A-Za-z_$][\w$]*$",name):
                    out.append(self.field_obj(name,name,"path_destructured",True))
        return self.unique(out)
    def header_fields(self,raw):
        out=[]
        # request.headers.authorization, ctx.headers.authorization, ctx.request.headers.authorization
        for m in re.finditer(r"(?:request|req|ctx|context|reply\.request)(?:\.request)?\.headers\.([A-Za-z_$][\w$-]*)",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"header_direct"))
        # request.headers['authorization']
        for m in re.finditer(r"(?:request|req|ctx|context|reply\.request)(?:\.request)?\.headers\s*\[\s*['\"]([^'\"]+)['\"]\s*\]",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"header_bracket"))
        # request.header('authorization'), request.get('authorization')
        for m in re.finditer(r"(?:request|req|ctx|context)\.(?:header|get)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"header_function"))
        # Fastify commonly exposes request.headers.authorization lowercase/normalized
        # Destructuring: const { authorization } = request.headers
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:request|req|ctx|context)(?:\.request)?\.headers",raw):
            for part in m.group(1).split(","):
                name=part.strip().split(":")[0].strip()
                if re.match(r"^[A-Za-z_$][\w$-]*$",name):
                    out.append(self.field_obj(name,name,"header_destructured"))
        return self.unique(out)

    def cookie_fields(self,raw):
        out=[]
        for m in re.finditer(r"(?:request|req|ctx|context)(?:\.request)?\.cookies?\.([A-Za-z_$][\w$-]*)",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"cookie_direct"))
        for m in re.finditer(r"(?:request|req|ctx|context)(?:\.request)?\.cookies?\s*\[\s*['\"]([^'\"]+)['\"]\s*\]",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"cookie_bracket"))
        for m in re.finditer(r"(?:request|req|ctx|context)\.cookies?\.get\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",raw):
            out.append(self.field_obj(m.group(1),m.group(0),"cookie_function"))
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:request|req|ctx|context)(?:\.request)?\.cookies?",raw):
            for part in m.group(1).split(","):
                name=part.strip().split(":")[0].strip()
                if re.match(r"^[A-Za-z_$][\w$-]*$",name):
                    out.append(self.field_obj(name,name,"cookie_destructured"))
        return self.unique(out)

    def unique(self,items):
        out=[]; seen=set()
        for i in items:
            n=i.get("name")
            if n and n not in seen:
                seen.add(n); out.append(i)
        return out
    def to_schema(self,fields,source):
        props={}; req=[]
        for f in fields:
            props[f["name"]]=dict(f["schema"])
            props[f["name"]]["x-qaira-source"]=source
            if f.get("required"): req.append(f["name"])
        return {"type":"object","required":sorted(set(req)),"properties":props} if props else {}
    def to_openapi_parameters(self,ctx):
        params=[]
        for loc_key,openapi_in in [("query","query"),("path","path"),("header","header"),("cookie","cookie")]:
            for f in ctx.get("contexts",{}).get(loc_key,[]):
                params.append({
                    "name":f["name"],
                    "in":openapi_in,
                    "required": True if openapi_in=="path" else bool(f.get("required")),
                    "schema":f.get("schema",{"type":"string"}),
                    "x-qaira-source":f.get("source"),"x-qaira-confidence":f.get("confidence")
                })
        return params



class ContractBuilder:
    def __init__(self,request_context_engine=None):
        self.request_context_engine=request_context_engine
    def run(self,routes,req_traces,res_traces,auth):
        req_by={x["routeId"]:x for x in req_traces}; res_by={x["routeId"]:x for x in res_traces}; contracts=[]
        for rt in routes:
            req_tr=req_by.get(rt["id"],{}); res_tr=res_by.get(rt["id"],{})
            req=req_tr.get("schema") or {}
            request_context={}
            parameters=[]
            if self.request_context_engine:
                request_context=self.request_context_engine.analyze_trace(rt,req_tr)
                parameters=self.request_context_engine.to_openapi_parameters(request_context)
                # Body schema comes only from body context for method with body.
                if rt["method"] in {"GET","HEAD","OPTIONS"}:
                    req={}
                elif request_context.get("contexts",{}).get("body"):
                    ctx_body_schema=self.request_context_engine.to_schema(request_context["contexts"]["body"],"request_context_body")
                    # merge context body with previously resolved object-shape/schema body
                    req=self.merge_schema(req,ctx_body_schema) if req else ctx_body_schema
            if rt["method"] in {"GET","HEAD","OPTIONS"}:
                req={}
            elif rt["method"]=="DELETE" and not req:
                req={}
            res=res_tr.get("schema") or {"type":"object","properties":{"id":{"type":"string","x-qaira-source":"fallback_minimal"}}}
            strategy="not_required" if rt["method"] in {"GET","HEAD","OPTIONS"} else ("resolved" if req else "unresolved")
            au=auth.get(rt["id"],{"required":False,"type":"none"})
            conf={"overall":round(0.55+(0.3 if strategy in {"resolved","not_required"} else 0)+(0.08 if "fallback_minimal" not in json.dumps(res) else 0.02),2),"requestStrategy":strategy,"responseStrategy":"inline_response" if "fallback_minimal" not in json.dumps(res) else "minimal_fallback"}
            c=Contract(api_id=api_id(rt["method"],rt["path"]),method=rt["method"],path=rt["path"],request_body=req,response_body=res,auth=au,source_mappings={"route":[f"{rt['file']}:{rt['line']}"]},confidence=conf,trace=[rt],request_trace=req_tr.get("trace",[]),response_trace=res_tr.get("trace",[]),parameters=parameters,request_context=request_context)
            c.curl=make_curl(c); contracts.append(c)
        return contracts
    def merge_schema(self,a,b):
        merged=json.loads(json.dumps(a or {"type":"object","properties":{},"required":[]}))
        merged.setdefault("type","object"); merged.setdefault("properties",{}); merged.setdefault("required",[])
        for k,v in (b or {}).get("properties",{}).items():
            if k not in merged["properties"]:
                merged["properties"][k]=v
        merged["required"]=sorted(set((merged.get("required") or []) + ((b or {}).get("required") or [])))
        return merged

class DiagnosticsAgent:
    def run(self,contracts,handler_report,body_report):
        body_expected=[c for c in contracts if c.method in {"POST","PUT","PATCH"}]
        body_detected=[c for c in body_expected if c.request_body]
        handler_counts={"totalRoutes":len(handler_report),"inlineDetected":len([x for x in handler_report if x.get("inlineHandlerDetected")]),"externalOrUnknown":len([x for x in handler_report if not x.get("inlineHandlerDetected")])}
        body_counts={"bodyExpected":len(body_expected),"bodyDetected":len(body_detected),"bodyFieldsDetected":sum(len((c.request_body.get("properties") or {})) for c in body_detected),"bodyDetectedButFieldsUnknown":len([c for c in body_detected if c.request_body and not (c.request_body.get("properties") or {})])}
        return handler_counts,body_counts,{"routes":body_report}

class DriftImpactAgent:
    def run(self,learning,contracts,changed):
        learning.mkdir(parents=True,exist_ok=True)
        prev_path=learning/"previous_contracts.json"; prev=[]
        if prev_path.exists():
            try: prev=json.loads(prev_path.read_text(encoding="utf-8"))
            except Exception: prev=[]
        current=[safe_json(c) for c in contracts]
        prev_path.write_text(json.dumps(current,indent=2),encoding="utf-8")
        return {"changedFiles":changed,"impactedApis":[]},{"driftItems":[],"breakingCount":0,"warningCount":0,"safeCount":0}

class LLMFallbackBundle:
    def run(self,fs,learning,contracts,drift,cfg):
        failures=[]
        for c in contracts:
            if c.method in {"POST","PUT","PATCH"} and not c.request_body:
                failures.append({"failureType":"payload_unresolved","wanted":"request payload schema","where":"inline_handler_body_trace","evidence":[safe_json(c)],"files":[x.split(":")[0] for x in c.source_mappings.get("route",[])]})
        attempts=[{"tool":x,"status":"success"} for x in ["InlineFastifyHandlerCompilerV32","RequestBodyAliasTracker","FastifySchemaExtractor","ContractBuilder"]]
        requests=[]; slices=[]
        for i,f in enumerate(failures,1):
            chunks=[]
            for file in f.get("files",[])[:3]:
                p=fs.src/file
                if p.exists(): chunks.append({"file":file,"lines":"\n".join(fs.read(p).splitlines()[:cfg["llm"].get("max_semantic_slice_lines",120)])})
            slices.append({"fallbackId":f"FB-{i:03d}","failureType":f["failureType"],"slices":chunks})
            requests.append({"fallbackId":f"FB-{i:03d}","failureType":f["failureType"],"what_we_wanted":f["wanted"],"what_we_tried":attempts,"what_worked":attempts,"what_failed":[],"where_trace_stopped":f["where"],"evidence_chain":f["evidence"],"semantic_slice_ref":f"FB-{i:03d}","exact_question":"Based only on the supplied inline handler slice, identify request body schema. Return strict JSON only.","llm_call_required":False,"status":"prepared_not_executed"})
        return failures,slices,requests,{"payload_unresolved":{"prepared":len(requests),"executed":0,"accepted":0}}


class ValidationChainResolver:
    def __init__(self,cfg,validation_registry):
        self.cfg=cfg
        self.validation=validation_registry or {"schemas":[]}
        self.inf=TypeInferencer(cfg)
        self.report=[]
    def recover(self,contract):
        raw=self.raw_from_contract(contract)
        if not raw:
            return None
        # schema.parse(request.body)
        candidates=[]
        patterns=[
            r"([A-Za-z_$][\w$]*)\.parse\s*\(\s*(?:request|req)\.body\s*\)",
            r"([A-Za-z_$][\w$]*)\.safeParse\s*\(\s*(?:request|req)\.body\s*\)",
            r"([A-Za-z_$][\w$]*)\.validate(?:Async)?\s*\(\s*(?:request|req)\.body\s*\)",
            r"validate\s*\(\s*([A-Za-z_$][\w$]*)\s*,\s*(?:request|req)\.body\s*\)",
            r"validateBody\s*\(\s*([A-Za-z_$][\w$]*)\s*,\s*(?:request|req)\.body\s*\)",
            r"bodySchema\s*:\s*([A-Za-z_$][\w$]*)",
            r"schema\s*:\s*\{[\s\S]{0,800}?body\s*:\s*([A-Za-z_$][\w$]*)"
        ]
        for pat in patterns:
            for m in re.finditer(pat,raw):
                candidates.append(m.group(1))
        for name in candidates:
            schema=self.find_schema(name)
            if schema:
                result={"apiId":contract.api_id,"path":contract.path,"method":contract.method,"strategy":"validation_chain_resolver","schema":schema.get("name"),"kind":schema.get("kind"),"confidence":0.94}
                self.report.append(result)
                return schema.get("schema")
        if candidates:
            self.report.append({"apiId":contract.api_id,"path":contract.path,"method":contract.method,"strategy":"validation_chain_schema_not_found","candidates":candidates,"confidence":0.3})
        return None
    def raw_from_contract(self,contract):
        for item in contract.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"):
                    return bi.get("rawHandler")
                if item.get("type")=="v34_schema_enrichment":
                    pass
        # nested trace variant
        for item in contract.request_trace or []:
            if isinstance(item,dict) and item.get("type") in {"inline_handler_body_analysis","regex_inline_body_analysis"}:
                return (item.get("bodyInfo") or {}).get("rawHandler","")
        return ""
    def find_schema(self,name):
        norm=re.sub(r"[^a-z0-9]","",str(name).lower())
        for s in self.validation.get("schemas",[]):
            sn=re.sub(r"[^a-z0-9]","",s.get("name","").lower())
            if sn==norm or sn.endswith(norm) or norm.endswith(sn):
                return s
        return None

class ServiceInputUsageResolver:
    def __init__(self,cfg,signature_registry=None,import_registry=None):
        self.cfg=cfg
        self.inf=TypeInferencer(cfg)
        self.signatures=(signature_registry or {}).get("signatures",[])
        self.imports=(import_registry or {}).get("imports",[])
        self.report=[]
    def recover(self,contract,fs):
        raw=self.raw_from_contract(contract)
        if not raw:
            return None
        aliases=self.body_aliases(raw)
        fields=set()
        # direct usage in route handler
        for a in aliases:
            fields.update(self.fields_used_on_alias(raw,a))
        # service call payload alias: authService.login(payload)
        service_calls=self.service_calls(raw,aliases)
        for sc in service_calls:
            svc_fields=self.resolve_service_usage(sc,fs)
            fields.update(svc_fields)
        if fields:
            schema={"type":"object","required":[],"properties":{}}
            for f in sorted(fields):
                field_schema=self.inf.infer(f,f)
                field_schema["x-qaira-source"]="service_input_usage"
                schema["properties"][f]=field_schema
            result={"apiId":contract.api_id,"path":contract.path,"method":contract.method,"strategy":"service_input_usage_resolver","fields":sorted(fields),"confidence":0.88}
            self.report.append(result)
            return schema
        self.report.append({"apiId":contract.api_id,"path":contract.path,"method":contract.method,"strategy":"service_input_usage_unresolved","serviceCalls":service_calls,"confidence":0.2})
        return None
    def raw_from_contract(self,contract):
        for item in contract.request_trace or []:
            if isinstance(item,dict) and item.get("type") in {"inline_handler_body_analysis","regex_inline_body_analysis"}:
                return (item.get("bodyInfo") or {}).get("rawHandler","")
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"):
                    return bi.get("rawHandler")
        return ""
    def body_aliases(self,raw):
        aliases={"body","request.body","req.body"}
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:request|req)\.body",raw):
            aliases.add(m.group(1))
        for m in re.finditer(r"(?:const|let|var)\s*\{[^}]*body[^}]*\}\s*=\s*(?:request|req)",raw):
            aliases.add("body")
        # schema.parse body alias: const payload = schema.parse(request.body)
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[A-Za-z_$][\w$]*\.(?:parse|safeParse|validateAsync|validate)\s*\(\s*(?:request|req)\.body\s*\)",raw):
            aliases.add(m.group(1))
        return aliases
    def fields_used_on_alias(self,raw,alias):
        fields=set()
        if alias in {"request.body","req.body"}:
            prefix=re.escape(alias)
            for m in re.finditer(prefix+r"\.([A-Za-z_$][\w$]*)",raw):
                fields.add(m.group(1))
        else:
            for m in re.finditer(r"\b"+re.escape(alias)+r"\.([A-Za-z_$][\w$]*)",raw):
                fields.add(m.group(1))
        return fields
    def service_calls(self,raw,aliases):
        calls=[]
        for alias in aliases:
            if not alias or "." in alias:
                continue
            for m in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(([^)]*\b"+re.escape(alias)+r"\b[^)]*)\)",raw):
                calls.append({"call":m.group(1),"args":m.group(2),"alias":alias})
        return calls
    def resolve_service_usage(self,service_call,fs):
        # Best-effort: find function with same method name and inspect alias usage inside it.
        method=service_call.get("call","").split(".")[-1]
        fields=set()
        for sig in self.signatures:
            if sig.get("name")==method or sig.get("qualifiedName","").endswith("."+method):
                file=sig.get("file")
                if not file: 
                    continue
                p=fs.src/file
                if not p.exists():
                    continue
                t=fs.read(p)
                block=self.extract_function_block(t,method)
                if not block:
                    continue
                # inspect first parameter name
                params=sig.get("params",[])
                aliases=[params[0].get("name")] if params else ["payload","body","data","input","dto"]
                for a in aliases:
                    if a:
                        fields.update(self.fields_used_on_alias(block,a))
        return fields
    def extract_function_block(self,t,method):
        pats=[
            r"(?:async\s+)?function\s+"+re.escape(method)+r"\s*\([^)]*\)\s*\{([\s\S]{0,6000}?)\n?\}",
            r"(?:const|let|var)\s+"+re.escape(method)+r"\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{([\s\S]{0,6000}?)\n?\}",
            re.escape(method)+r"\s*:\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{([\s\S]{0,6000}?)\n?\}",
            re.escape(method)+r"\s*\([^)]*\)\s*\{([\s\S]{0,6000}?)\n?\}"
        ]
        for pat in pats:
            m=re.search(pat,t)
            if m:
                return m.group(1)
        return ""


class SchemaAttachmentResolver:
    def __init__(self,cfg,validation_registry):
        self.cfg=cfg
        self.validation=validation_registry or {"schemas":[]}
        self.report=[]
        self.registry=[]
        self.diagnostics={"routesChecked":0,"attachmentsFound":0,"schemasResolved":0,"unresolvedSchemaRefs":0}
    def run(self,contracts,fs):
        for c in contracts:
            self.diagnostics["routesChecked"]+=1
            if c.method in {"GET","HEAD","OPTIONS"}:
                continue
            if c.request_body and (c.request_body.get("properties") or {}):
                continue
            raw=self.raw_from_contract(c)
            file=self.file_from_contract(c)
            extra_raw=""
            if file:
                p=fs.src/file
                if p.exists():
                    extra_raw=fs.read(p)
            attachment=self.find_attachment(c,raw,extra_raw)
            if attachment:
                self.diagnostics["attachmentsFound"]+=1
                schema=self.resolve_schema_attachment(attachment)
                if schema:
                    self.diagnostics["schemasResolved"]+=1
                    c.request_body=schema.get("schema",schema)
                    c.confidence["requestStrategy"]="schema_attachment_resolver"
                    c.confidence["overall"]=max(c.confidence.get("overall",0),0.93)
                    c.curl=make_curl(c)
                    item={"apiId":c.api_id,"method":c.method,"path":c.path,"strategy":"schema_attachment_resolver","schemaRef":attachment.get("schemaRef"),"schema":schema.get("name"),"kind":schema.get("kind"),"confidence":0.93,"source":attachment.get("source")}
                    self.report.append(item)
                    self.registry.append(item)
                else:
                    self.diagnostics["unresolvedSchemaRefs"]+=1
                    self.report.append({"apiId":c.api_id,"method":c.method,"path":c.path,"strategy":"schema_attachment_unresolved_ref","schemaRef":attachment.get("schemaRef"),"source":attachment.get("source")})
        return {"attachments":self.report,"diagnostics":self.diagnostics}
    def raw_from_contract(self,c):
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"):
                    return bi.get("rawHandler")
                if item.get("type") in {"inline_handler_body_analysis","regex_inline_body_analysis"}:
                    return (item.get("bodyInfo") or {}).get("rawHandler","")
        return ""
    def file_from_contract(self,c):
        try:
            return (c.source_mappings.get("route") or [""])[0].split(":")[0]
        except Exception:
            return ""
    def find_attachment(self,c,raw,full_file_text):
        text=(raw or "") + "\n" + (full_file_text or "")
        path=re.escape(c.path.replace("{id}",":id"))
        # fastify.post('/x', { schema: loginSchema }, handler) / schema:{body: x}
        route_literal_patterns=[
            re.escape(c.path),
            re.escape(c.path.replace("{id}",":id")),
            re.escape(c.path.replace("{id}","${id}")),
        ]
        for rp in route_literal_patterns:
            # method call with route literal and options block
            pat=r"(?:fastify|app|router|server)\."+c.method.lower()+r"\s*\(\s*['\"`]"+rp+r"['\"`]\s*,\s*([\s\S]{0,3500}?)\)"
            for m in re.finditer(pat,text,re.I):
                att=self.schema_ref_from_options(m.group(1),"fastify_method_options")
                if att: return att
            # fastify.route({ method:'POST', url:'/x', schema: ...})
            pat2=r"(?:fastify|app|router|server)\.route\s*\(\s*\{([\s\S]{0,5000}?method\s*:\s*['\"`]"+c.method+r"['\"`][\s\S]{0,5000}?url\s*:\s*['\"`]"+rp+r"['\"`][\s\S]{0,5000}?)\}\s*\)"
            for m in re.finditer(pat2,text,re.I):
                att=self.schema_ref_from_options(m.group(1),"fastify_route_object")
                if att: return att
        # route has opts variable: fastify.post('/x', opts, handler)
        for rp in route_literal_patterns:
            pat3=r"(?:fastify|app|router|server)\."+c.method.lower()+r"\s*\(\s*['\"`]"+rp+r"['\"`]\s*,\s*([A-Za-z_$][\w$]*)"
            for m in re.finditer(pat3,text,re.I):
                var=m.group(1)
                block=self.find_variable_object(text,var)
                if block:
                    att=self.schema_ref_from_options(block,"route_options_variable")
                    if att: return att
        # exported object route option fallback in same file
        for ex_pat in [
            r"module\.exports\s*=\s*\{([\s\S]{0,4000}?)\}",
            r"export\s+const\s+[A-Za-z_$][\w$]*\s*=\s*\{([\s\S]{0,4000}?)\}",
            r"export\s+default\s+\{([\s\S]{0,4000}?)\}"
        ]:
            for m in re.finditer(ex_pat,text):
                att=self.schema_ref_from_options(m.group(1),"exported_route_options")
                if att: return att
        return None
    def find_variable_object(self,text,var):
        # const opts = { ... }
        pat=r"(?:const|let|var)\s+"+re.escape(var)+r"\s*=\s*\{([\s\S]{0,5000}?)\}\s*;?"
        m=re.search(pat,text)
        return m.group(1) if m else ""
    def schema_ref_from_options(self,options,source):
        if not options:
            return None
        # schema: { body: loginSchema }
        m=re.search(r"schema\s*:\s*\{[\s\S]{0,2500}?body\s*:\s*([A-Za-z_$][\w$]*)",options)
        if m: return {"schemaRef":m.group(1),"source":source+"_body"}
        # schema: loginSchema
        m=re.search(r"schema\s*:\s*([A-Za-z_$][\w$]*)",options)
        if m: return {"schemaRef":m.group(1),"source":source+"_schema"}
        # body: loginSchema direct
        m=re.search(r"body\s*:\s*([A-Za-z_$][\w$]*)",options)
        if m: return {"schemaRef":m.group(1),"source":source+"_direct_body"}
        # inline JSON schema body: { body:{ type:'object', properties:{...}} }
        props=re.search(r"body\s*:\s*\{[\s\S]{0,2500}?properties\s*:\s*\{([\s\S]{0,2000}?)\}",options)
        if props:
            fields=[]
            for fm in re.finditer(r"([A-Za-z_$][\w$]*)\s*:",props.group(1)):
                fields.append(fm.group(1))
            if fields:
                schema={"name":"inline_body_schema","kind":"inline_json_schema","schema":{"type":"object","required":[],"properties":{f:{"type":"string","x-qaira-source":"inline_route_schema"} for f in sorted(set(fields))}}}
                return {"schemaRef":"<inline_body_schema>","source":source+"_inline_json_schema","inlineSchema":schema}
        return None
    def resolve_schema_attachment(self,att):
        if att.get("inlineSchema"):
            return att["inlineSchema"]
        ref=att.get("schemaRef")
        return self.find_schema(ref)
    def find_schema(self,name):
        norm=re.sub(r"[^a-z0-9]","",str(name).lower())
        for s in self.validation.get("schemas",[]):
            sn=re.sub(r"[^a-z0-9]","",s.get("name","").lower())
            if sn==norm or sn.endswith(norm) or norm.endswith(sn):
                return s
        return None


class UnresolvedRouteInvestigator:
    def __init__(self,cfg,validation_registry,signature_registry=None,import_registry=None):
        self.cfg=cfg
        self.validation_resolver=ValidationChainResolver(cfg,validation_registry)
        self.service_usage_resolver=ServiceInputUsageResolver(cfg,signature_registry,import_registry)
        self.report=[]
    def run(self,contracts,fs):
        unresolved=[]
        recovered=[]
        for c in contracts:
            if c.method in {"GET","HEAD","OPTIONS"}:
                continue
            if c.request_body and (c.request_body.get("properties") or {}):
                continue
            unresolved.append(c)
            validation_schema=self.validation_resolver.recover(c)
            service_schema=None if validation_schema else self.service_usage_resolver.recover(c,fs)
            schema=validation_schema or service_schema
            strategy="validation_chain_resolver" if validation_schema else ("service_input_usage_resolver" if service_schema else "unresolved")
            item={"apiId":c.api_id,"method":c.method,"path":c.path,"strategy":strategy,"recovered":bool(schema),"fields":list((schema or {}).get("properties",{}).keys())}
            self.report.append(item)
            if schema:
                c.request_body=schema
                c.confidence["requestStrategy"]=strategy
                c.confidence["overall"]=max(c.confidence.get("overall",0),0.87)
                c.curl=make_curl(c)
                recovered.append(c)
        return {
            "unresolvedBefore":len(unresolved),
            "recovered":len(recovered),
            "unresolvedAfter":len(unresolved)-len(recovered),
            "items":self.report
        }, recovered



class DiagnosticClassifier:
    def __init__(self,cfg):
        self.cfg=cfg
        self.classifications=[]
        self.summary={}
    def run(self,contracts):
        buckets={
            "body_not_expected":[],
            "already_has_body":[],
            "schema_in_handler_candidate":[],
            "validation_wrapper_candidate":[],
            "service_trace_required":[],
            "object_shape_candidate":[],
            "query_only_route":[],
            "path_only_route":[],
            "dynamic_runtime_only":[],
            "real_unresolved":[]
        }
        for c in contracts:
            item=self.classify(c)
            self.classifications.append(item)
            buckets[item["bucket"]].append(item)
        self.summary={k:len(v) for k,v in buckets.items()}
        self.summary["totalRoutes"]=len(contracts)
        self.summary["realUnresolvedPayloadRoutes"]=len(buckets["real_unresolved"])
        self.summary["actionableUnresolvedRoutes"]=len(buckets["real_unresolved"])+len(buckets["service_trace_required"])+len(buckets["validation_wrapper_candidate"])+len(buckets["schema_in_handler_candidate"])
        return {"summary":self.summary,"buckets":buckets,"items":self.classifications}
    def classify(self,c):
        method=c.method
        has_body=bool(c.request_body and (c.request_body.get("properties") or {}))
        ctx=c.request_context or {}
        counts=ctx.get("counts",{}) if isinstance(ctx,dict) else {}
        raw=self.raw_from_contract(c)
        base={"apiId":c.api_id,"method":c.method,"path":c.path,"hasRequestBody":has_body,"requestStrategy":c.confidence.get("requestStrategy"),"contextCounts":counts}
        if method in {"GET","HEAD","OPTIONS"}:
            return {**base,"bucket":"body_not_expected","reason":"HTTP method does not normally carry request body","nextAction":"Do not attempt body recovery. Validate query/path/header parameters only."}
        if method=="DELETE" and not self.has_body_signal(raw,c):
            return {**base,"bucket":"body_not_expected","reason":"DELETE route has no body signal; path params likely sufficient","nextAction":"Do not treat as unresolved payload unless request.body is used."}
        if has_body:
            return {**base,"bucket":"already_has_body","reason":"Request body schema already exists","nextAction":"No payload recovery needed."}
        if counts.get("query",0)>0 and counts.get("body",0)==0 and method in {"GET","DELETE"}:
            return {**base,"bucket":"query_only_route","reason":"Only query/path context detected, no body context","nextAction":"Generate parameters, not request body."}
        if counts.get("path",0)>0 and counts.get("body",0)==0 and method in {"DELETE"}:
            return {**base,"bucket":"path_only_route","reason":"Path-param-driven route","nextAction":"No request body required."}
        if self.has_schema_signal(raw):
            return {**base,"bucket":"schema_in_handler_candidate","reason":"Handler contains schema/validator references but resolver did not attach schema","nextAction":"Improve SchemaAttachmentResolver / ValidationChainResolver for this pattern."}
        if self.has_validation_wrapper_signal(raw):
            return {**base,"bucket":"validation_wrapper_candidate","reason":"Validation abstraction detected","nextAction":"Trace validate/validateBody/parser wrapper implementation."}
        if self.has_service_signal(raw):
            return {**base,"bucket":"service_trace_required","reason":"Body/payload passed to service, but service usage did not resolve","nextAction":"Improve service input usage tracing for this service call."}
        if self.has_object_shape_signal(raw):
            return {**base,"bucket":"object_shape_candidate","reason":"Object construction exists but was not converted into schema","nextAction":"Improve ObjectShapeAnalyzer for this local object pattern."}
        if self.has_dynamic_signal(raw):
            return {**base,"bucket":"dynamic_runtime_only","reason":"Dynamic keys / Object.keys / spread-only body detected","nextAction":"Mark partial, consider runtime/proxy capture or LLM micro-analysis."}
        return {**base,"bucket":"real_unresolved","reason":"No deterministic body/schema/service/object-shape signal found","nextAction":"Needs manual review or semantic slice LLM fallback."}
    def raw_from_contract(self,c):
        chunks=[]
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"):
                    chunks.append(bi.get("rawHandler"))
                nested=item.get("resolution",{})
                if isinstance(nested,dict):
                    chunks.append(json.dumps(nested))
        return "\n".join(chunks)
    def has_body_signal(self,raw,c):
        if c.request_context and c.request_context.get("counts",{}).get("body",0)>0:
            return True
        return bool(re.search(r"(?:request|req)\.body|\bbody\b",raw or ""))
    def has_schema_signal(self,raw):
        return bool(re.search(r"\bschema\b|bodySchema|requestSchema|responseSchema|z\.object|Joi\.object|Type\.Object|yup\.object",raw or "",re.I))
    def has_validation_wrapper_signal(self,raw):
        return bool(re.search(r"\b(validate|validateBody|validateRequest|parse|safeParse|validateAsync|schemaValidate|validator)\s*\(",raw or ""))
    def has_service_signal(self,raw):
        return bool(re.search(r"[A-Za-z_$][\w$]*(?:Service|Repo|Repository|Model|Client)?\.[A-Za-z_$][\w$]*\s*\(",raw or ""))
    def has_object_shape_signal(self,raw):
        return bool(re.search(r"(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*\{|[A-Za-z_$][\w$]*\s*\(\s*\{",raw or ""))
    def has_dynamic_signal(self,raw):
        return bool(re.search(r"Object\.keys|Object\.entries|reduce\s*\(|forEach\s*\(|\.\.\.(?:request|req)\.body|\.\.\.body",raw or ""))

class NextActionReportBuilder:
    def run(self,classification_report):
        summary=classification_report.get("summary",{})
        recommendations=[]
        if summary.get("body_not_expected",0):
            recommendations.append({"priority":1,"area":"Stop counting body-not-expected routes as unresolved","evidence":summary.get("body_not_expected"),"action":"Exclude GET/HEAD/OPTIONS and DELETE-without-body-signal from payload unresolved metrics."})
        if summary.get("schema_in_handler_candidate",0):
            recommendations.append({"priority":2,"area":"Schema linker gaps","evidence":summary.get("schema_in_handler_candidate"),"action":"Inspect schema_in_handler_candidate routes and add exact schema attachment pattern."})
        if summary.get("validation_wrapper_candidate",0):
            recommendations.append({"priority":3,"area":"Validation wrapper tracing","evidence":summary.get("validation_wrapper_candidate"),"action":"Trace validate/validateBody wrappers to schema argument and body argument."})
        if summary.get("service_trace_required",0):
            recommendations.append({"priority":4,"area":"Service input tracing","evidence":summary.get("service_trace_required"),"action":"Improve service function block extraction and parameter alias usage."})
        if summary.get("object_shape_candidate",0):
            recommendations.append({"priority":5,"area":"Object shape parsing","evidence":summary.get("object_shape_candidate"),"action":"Add shape pattern for unresolved object construction forms."})
        if summary.get("dynamic_runtime_only",0):
            recommendations.append({"priority":6,"area":"Runtime-only/dynamic payloads","evidence":summary.get("dynamic_runtime_only"),"action":"Mark partial and optionally use runtime proxy or constrained LLM semantic slice."})
        if summary.get("real_unresolved",0):
            recommendations.append({"priority":7,"area":"True unknowns","evidence":summary.get("real_unresolved"),"action":"Generate semantic slices for manual/LLM review."})
        return {"summary":summary,"recommendations":recommendations}



class ValidationWrapperResolverV48:
    def __init__(self,cfg,validation_registry):
        self.cfg=cfg
        self.validation=validation_registry or {"schemas":[]}
        self.inf=TypeInferencer(cfg)
        self.report=[]
    def recover(self,contract):
        raw=self.raw_from_contract(contract)
        if not raw:
            self.report.append({"apiId":contract.api_id,"path":contract.path,"method":contract.method,"status":"no_raw_handler"})
            return None
        candidates=self.find_schema_candidates(raw)
        for cand in candidates:
            schema=self.find_schema(cand.get("schemaRef"))
            if schema:
                result={
                    "apiId":contract.api_id,
                    "method":contract.method,
                    "path":contract.path,
                    "status":"resolved",
                    "strategy":"validation_wrapper_resolver_v48",
                    "pattern":cand.get("pattern"),
                    "schemaRef":cand.get("schemaRef"),
                    "schema":schema.get("name"),
                    "kind":schema.get("kind"),
                    "confidence":0.95
                }
                self.report.append(result)
                return schema.get("schema")
        if candidates:
            self.report.append({"apiId":contract.api_id,"method":contract.method,"path":contract.path,"status":"schema_ref_unresolved","candidates":candidates})
        else:
            self.report.append({"apiId":contract.api_id,"method":contract.method,"path":contract.path,"status":"no_validation_wrapper_pattern"})
        return None
    def raw_from_contract(self,c):
        chunks=[]
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"):
                    chunks.append(bi.get("rawHandler"))
                if item.get("type") in {"inline_handler_body_analysis","regex_inline_body_analysis"}:
                    chunks.append((item.get("bodyInfo") or {}).get("rawHandler",""))
        return "\n".join([x for x in chunks if x])
    def find_schema_candidates(self,raw):
        out=[]
        patterns=[
            ("schema_dot_parse", r"([A-Za-z_$][\w$]*)\.(?:parse|safeParse|validate|validateAsync)\s*\(\s*(?:request|req)\.body\s*\)"),
            ("validate_schema_body", r"\b(?:validate|validateBody|validateRequest|schemaValidate|validator)\s*\(\s*([A-Za-z_$][\w$]*)\s*,\s*(?:request|req)\.body\s*\)"),
            ("validate_body_schema", r"\b(?:validate|validateBody|validateRequest|schemaValidate|validator)\s*\(\s*(?:request|req)\.body\s*,\s*([A-Za-z_$][\w$]*)\s*\)"),
            ("const_payload_schema_parse", r"(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*([A-Za-z_$][\w$]*)\.(?:parse|safeParse|validate|validateAsync)\s*\(\s*(?:request|req)\.body\s*\)"),
            ("destructure_value_schema_validate", r"\{\s*value\s*\}\s*=\s*([A-Za-z_$][\w$]*)\.validate\s*\(\s*(?:request|req)\.body\s*\)"),
            ("await_validate_schema_body", r"await\s+(?:validate|validateBody|validateRequest)\s*\(\s*([A-Za-z_$][\w$]*)\s*,\s*(?:request|req)\.body\s*\)")
        ]
        for name,pat in patterns:
            for m in re.finditer(pat,raw):
                out.append({"pattern":name,"schemaRef":m.group(1)})
        # detect schema object aliases: const schema = loginSchema; validate(schema, request.body)
        alias_map={}
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*(?:Schema|Dto|DTO|Validator|Body))",raw):
            alias_map[m.group(1)]=m.group(2)
        expanded=[]
        for cand in out:
            ref=cand.get("schemaRef")
            if ref in alias_map:
                cand=dict(cand); cand["schemaRef"]=alias_map[ref]; cand["alias"]=ref
            expanded.append(cand)
        return expanded
    def find_schema(self,name):
        if not name:
            return None
        norm=re.sub(r"[^a-z0-9]","",str(name).lower())
        for s in self.validation.get("schemas",[]):
            sn=re.sub(r"[^a-z0-9]","",s.get("name","").lower())
            if sn==norm or sn.endswith(norm) or norm.endswith(sn):
                return s
        return None


class ExportResolverV49:
    def __init__(self,cfg):
        self.cfg=cfg
        self.report=[]
        self.registry=[]
    def build_registry(self,fs):
        registry={}
        for p in fs.all_files():
            if p.suffix.lower() not in {".js",".jsx",".ts",".tsx"}:
                continue
            file=fs.rel(p); text=fs.read(p)
            impls=self.extract_implementations(file,text)
            registry[file]=impls
            self.registry += impls
        self.report.append({"filesIndexed":len(registry),"implementations":len(self.registry)})
        return registry
    def extract_implementations(self,file,text):
        impls=[]
        # named function / const arrow
        for m in re.finditer(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{",text):
            impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,m.start()),"function_declaration"))
        for m in re.finditer(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",text):
            impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,m.start()),"arrow_function"))
        # object literal methods: const service = { create(payload) {}, create: async (payload) => {} }
        for om in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\{([\s\S]{0,12000}?)\n?\}",text):
            obj=om.group(1); body=om.group(2)
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{",body):
                impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,om.start()+m.start()),"object_literal_method",service_object=obj))
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",body):
                impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,om.start()+m.start()),"object_literal_arrow",service_object=obj))
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$]*)",body):
                impls.append({"file":file,"name":m.group(1),"targetName":m.group(2),"line":line_no(text,om.start()+m.start()),"kind":"object_method_reference","serviceObject":obj,"params":[]})
        # class methods
        for cm in re.finditer(r"class\s+([A-Za-z_$][\w$]*)[\s\S]*?\{([\s\S]{0,16000}?)\n?\}",text):
            cls=cm.group(1); body=cm.group(2)
            for m in re.finditer(r"(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{",body):
                if m.group(1) in {"if","for","while","switch","catch"}:
                    continue
                impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,cm.start()+m.start()),"class_method",class_name=cls))
        # module.exports object inline function: module.exports = { create: async (payload)=>{} }
        for ex in re.finditer(r"module\.exports\s*=\s*\{([\s\S]{0,14000}?)\n?\}",text):
            body=ex.group(1)
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",body):
                impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,ex.start()+m.start()),"commonjs_export_object_arrow"))
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{",body):
                impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,ex.start()+m.start()),"commonjs_export_object_method"))
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$]*)",body):
                impls.append({"file":file,"name":m.group(1),"targetName":m.group(2),"line":line_no(text,ex.start()+m.start()),"kind":"commonjs_export_reference","params":[]})
        # exports.x = async function(payload) / module.exports.x = ...
        for m in re.finditer(r"(?:exports|module\.exports)\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function\s*\(([^)]*)\)\s*\{",text):
            impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,m.start()),"commonjs_property_function"))
        for m in re.finditer(r"(?:exports|module\.exports)\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",text):
            impls.append(self.impl(file,m.group(1),m.group(2),line_no(text,m.start()),"commonjs_property_arrow"))
        for m in re.finditer(r"(?:exports|module\.exports)\.([A-Za-z_$][\w$]*)\s*=\s*([A-Za-z_$][\w$]*)",text):
            impls.append({"file":file,"name":m.group(1),"targetName":m.group(2),"line":line_no(text,m.start()),"kind":"commonjs_property_reference","params":[]})
        return impls
    def impl(self,file,name,params,line,kind,service_object=None,class_name=None):
        parsed=[]
        for raw in [x.strip() for x in params.split(",") if x.strip()]:
            pname=raw.split(":")[0].split("=")[0].replace("?","").strip()
            parsed.append({"name":pname,"raw":raw})
        return {"file":file,"name":name,"line":line,"kind":kind,"params":parsed,"serviceObject":service_object,"className":class_name}

class ImportAwareServiceResolverV49:
    def __init__(self,cfg,import_registry,export_registry):
        self.cfg=cfg
        self.imports=(import_registry or {}).get("imports",[])
        self.exports=(import_registry or {}).get("exports",[])
        self.export_registry=export_registry or {}
        self.report=[]
    def resolve(self,caller_file,call):
        raw=call or ""
        parts=raw.split(".")
        if len(parts)<2:
            impl=self.find_impl_in_file(caller_file,raw)
            self.report.append({"callerFile":caller_file,"call":raw,"strategy":"same_file","resolved":bool(impl),"implementation":impl})
            return impl
        local=parts[0]; method=parts[-1]
        imp=self.find_import(caller_file,local)
        candidate_files=[]
        if imp and imp.get("resolvedFile"):
            candidate_files.append(imp["resolvedFile"])
            # include re-export/barrel targets
            for ex in self.exports:
                if ex.get("file")==imp["resolvedFile"] and ex.get("resolvedFile"):
                    candidate_files.append(ex["resolvedFile"])
        else:
            # fallback: local may equal service file name-ish
            candidate_files=[]
        for file in list(dict.fromkeys(candidate_files)):
            impl=self.find_impl_in_file(file,method)
            if impl:
                self.report.append({"callerFile":caller_file,"call":raw,"strategy":"import_aware_service_method","import":imp,"resolved":True,"implementation":impl})
                return impl
            ref=self.find_reference_in_file(file,method)
            if ref:
                target=ref.get("targetName")
                impl=self.find_impl_in_file(file,target)
                if impl:
                    self.report.append({"callerFile":caller_file,"call":raw,"strategy":"import_aware_export_reference","import":imp,"reference":ref,"resolved":True,"implementation":impl})
                    return impl
        self.report.append({"callerFile":caller_file,"call":raw,"strategy":"import_aware_unresolved","import":imp,"candidateFiles":candidate_files,"method":method,"resolved":False})
        return None
    def find_import(self,file,local):
        for im in self.imports:
            if im.get("file")==file and im.get("local")==local:
                return im
        return None
    def find_impl_in_file(self,file,method):
        for impl in self.export_registry.get(file,[]):
            if impl.get("name")==method:
                if impl.get("targetName"):
                    return self.find_impl_in_file(file,impl.get("targetName")) or impl
                return impl
        return None
    def find_reference_in_file(self,file,method):
        for impl in self.export_registry.get(file,[]):
            if impl.get("name")==method and impl.get("targetName"):
                return impl
        return None


class ServiceSemanticTracerV48:
    def __init__(self,cfg,signature_registry=None,import_registry=None,service_resolver=None):
        self.cfg=cfg
        self.inf=TypeInferencer(cfg)
        self.signatures=(signature_registry or {}).get("signatures",[])
        self.imports=(import_registry or {}).get("imports",[])
        self.service_resolver=service_resolver
        self.report=[]
    def recover(self,contract,fs):
        raw=self.raw_from_contract(contract)
        if not raw:
            self.report.append({"apiId":contract.api_id,"path":contract.path,"method":contract.method,"status":"no_raw_handler"})
            return None
        aliases=self.body_aliases(raw)
        service_calls=self.find_service_calls(raw,aliases)
        fields=set()
        evidence=[]
        # direct route handler alias usage first
        for a in aliases:
            direct=self.fields_used_on_alias(raw,a)
            if direct:
                fields.update(direct)
                evidence.append({"source":"route_handler_alias_usage","alias":a,"fields":sorted(direct)})
        caller_file=self.file_from_contract(contract)
        for call in service_calls:
            call["callerFile"]=caller_file
            resolved=self.trace_service_call(call,fs)
            if resolved.get("fields"):
                fields.update(resolved["fields"])
            evidence.append(resolved)
        if fields:
            schema={"type":"object","required":[],"properties":{}}
            for f in sorted(fields):
                field_schema=self.inf.infer(f,f)
                field_schema["x-qaira-source"]="service_semantic_tracer_v48"
                schema["properties"][f]=field_schema
            self.report.append({"apiId":contract.api_id,"method":contract.method,"path":contract.path,"status":"resolved","strategy":"service_semantic_tracer_v48","fields":sorted(fields),"serviceCalls":service_calls,"evidence":evidence,"confidence":0.9})
            return schema
        self.report.append({"apiId":contract.api_id,"method":contract.method,"path":contract.path,"status":"unresolved","serviceCalls":service_calls,"evidence":evidence})
        return None
    def raw_from_contract(self,c):
        chunks=[]
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"):
                    chunks.append(bi.get("rawHandler"))
                if item.get("type") in {"inline_handler_body_analysis","regex_inline_body_analysis"}:
                    chunks.append((item.get("bodyInfo") or {}).get("rawHandler",""))
        return "\n".join([x for x in chunks if x])
    def body_aliases(self,raw):
        aliases={"body","payload","data","input","dto","request.body","req.body"}
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:request|req)\.body",raw):
            aliases.add(m.group(1))
        for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[A-Za-z_$][\w$]*\.(?:parse|safeParse|validate|validateAsync)\s*\(\s*(?:request|req)\.body\s*\)",raw):
            aliases.add(m.group(1))
        return aliases
    def find_service_calls(self,raw,aliases):
        calls=[]
        for alias in aliases:
            if not alias or "." in alias:
                continue
            for m in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(([^)]*\b"+re.escape(alias)+r"\b[^)]*)\)",raw):
                calls.append({"call":m.group(1),"args":m.group(2),"alias":alias})
        # direct request.body passed
        for m in re.finditer(r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(([^)]*(?:request|req)\.body[^)]*)\)",raw):
            calls.append({"call":m.group(1),"args":m.group(2),"alias":"request.body"})
        # dedupe
        seen=set(); out=[]
        for c in calls:
            key=(c["call"],c["args"],c["alias"])
            if key not in seen:
                seen.add(key); out.append(c)
        return out
    def file_from_contract(self,c):
        try:
            return (c.source_mappings.get("route") or [""])[0].split(":")[0]
        except Exception:
            return ""

    def trace_service_call(self,call,fs):
        method=call.get("call","").split(".")[-1]
        result={"call":call,"method":method,"status":"not_found","fields":[]}
        if self.service_resolver:
            caller_file=call.get("callerFile") or call.get("file") or ""
            impl=self.service_resolver.resolve(caller_file,call.get("call","")) if caller_file else None
            if impl:
                file=impl.get("file")
                p=fs.src/file
                if p.exists():
                    text=fs.read(p)
                    block=self.extract_method_block(text,impl.get("name") or method)
                    param_aliases=[pinfo.get("name") for pinfo in impl.get("params",[]) if pinfo.get("name")] or ["payload","body","data","input","dto"]
                    fields=set()
                    for a in param_aliases:
                        fields.update(self.fields_used_on_alias(block,a))
                        fields.update(self.fields_destructured_from_alias(block,a))
                    if fields:
                        return {"call":call,"method":method,"status":"resolved_import_aware","file":file,"line":impl.get("line"),"fields":sorted(fields),"paramAliases":param_aliases,"implementation":impl}
                    result={"call":call,"method":method,"status":"import_aware_method_found_no_fields","file":file,"line":impl.get("line"),"paramAliases":param_aliases,"fields":[],"implementation":impl}
        for sig in self.signatures:
            if not (sig.get("name")==method or sig.get("qualifiedName","").endswith("."+method)):
                continue
            file=sig.get("file")
            if not file:
                continue
            p=fs.src/file
            if not p.exists():
                continue
            text=fs.read(p)
            block=self.extract_method_block(text,method)
            if not block:
                continue
            param_aliases=[]
            for pinfo in sig.get("params",[]):
                if pinfo.get("name"):
                    param_aliases.append(pinfo["name"])
            if not param_aliases:
                param_aliases=["payload","body","data","input","dto","request"]
            fields=set()
            for a in param_aliases:
                fields.update(self.fields_used_on_alias(block,a))
                fields.update(self.fields_destructured_from_alias(block,a))
            if fields:
                return {"call":call,"method":method,"status":"resolved","file":file,"line":sig.get("line"),"fields":sorted(fields),"paramAliases":param_aliases}
            result={"call":call,"method":method,"status":"method_found_no_fields","file":file,"line":sig.get("line"),"paramAliases":param_aliases,"fields":[]}
        return result
    def extract_method_block(self,text,method):
        patterns=[
            r"(?:async\s+)?function\s+"+re.escape(method)+r"\s*\([^)]*\)\s*\{([\s\S]{0,10000}?)\n?\}",
            r"(?:const|let|var)\s+"+re.escape(method)+r"\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{([\s\S]{0,10000}?)\n?\}",
            re.escape(method)+r"\s*:\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{([\s\S]{0,10000}?)\n?\}",
            re.escape(method)+r"\s*\([^)]*\)\s*\{([\s\S]{0,10000}?)\n?\}"
        ]
        for pat in patterns:
            m=re.search(pat,text)
            if m:
                return m.group(1)
        return ""
    def fields_used_on_alias(self,raw,alias):
        fields=set()
        if alias in {"request.body","req.body"}:
            for m in re.finditer(re.escape(alias)+r"\.([A-Za-z_$][\w$]*)",raw):
                fields.add(m.group(1))
        else:
            for m in re.finditer(r"\b"+re.escape(alias)+r"\.([A-Za-z_$][\w$]*)",raw):
                fields.add(m.group(1))
        return fields
    def fields_destructured_from_alias(self,raw,alias):
        fields=set()
        if not alias or "." in alias:
            return fields
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*"+re.escape(alias),raw):
            for part in m.group(1).split(","):
                name=part.strip().split(":")[0].strip()
                if re.match(r"^[A-Za-z_$][\w$]*$",name):
                    fields.add(name)
        return fields

class ActionableRecoveryEngineV48:
    def __init__(self,cfg,validation_registry,signature_registry=None,import_registry=None,service_resolver=None):
        self.validation_wrapper=ValidationWrapperResolverV48(cfg,validation_registry)
        self.service_tracer=ServiceSemanticTracerV48(cfg,signature_registry,import_registry,service_resolver)
        self.report=[]
    def run(self,contracts,classification_report,fs):
        buckets=(classification_report or {}).get("buckets",{})
        target_ids=set()
        for bucket in ["validation_wrapper_candidate","service_trace_required"]:
            for item in buckets.get(bucket,[]):
                target_ids.add(item.get("apiId"))
        recovered=[]
        for c in contracts:
            if c.api_id not in target_ids:
                continue
            schema=None
            strategy=None
            # Prefer validation wrapper for validation candidates.
            schema=self.validation_wrapper.recover(c)
            if schema:
                strategy="validation_wrapper_resolver_v48"
            else:
                schema=self.service_tracer.recover(c,fs)
                if schema:
                    strategy="service_semantic_tracer_v48"
            if schema:
                c.request_body=schema
                c.confidence["requestStrategy"]=strategy
                c.confidence["overall"]=max(c.confidence.get("overall",0),0.90)
                c.curl=make_curl(c)
                recovered.append(c)
                self.report.append({"apiId":c.api_id,"method":c.method,"path":c.path,"recovered":True,"strategy":strategy,"fields":list(schema.get("properties",{}).keys())})
            else:
                self.report.append({"apiId":c.api_id,"method":c.method,"path":c.path,"recovered":False})
        return {
            "targetedRoutes":len(target_ids),
            "recovered":len(recovered),
            "unrecovered":len(target_ids)-len(recovered),
            "items":self.report
        }, recovered


class ArtifactGenerator:
    def run(self,contracts,store):
        store.text("generated/generated_curls.sh",self.curls(contracts))
        store.json("generated/openapi.json",self.openapi(contracts))
        store.json("generated/postman_collection.json",self.postman(contracts))
        store.json("generated/qaira_api_repository.json",{"version":"58.0","apis":[safe_json(c) for c in contracts]})
    def curls(self,contracts):
        lines=["#!/usr/bin/env bash","set -euo pipefail",': "${baseUrl:=http://localhost:3000}"',': "${token:=CHANGE_ME}"',""]
        for c in contracts: lines += [f"echo '### {c.method} {c.path}'",c.curl.replace("{{baseUrl}}","${baseUrl}").replace("{{token}}","${token}"),""]
        return "\n".join(lines)
    def openapi(self,contracts):
        paths={}
        for c in contracts:
            op={"summary":c.api_id,"x-qaira-confidence":c.confidence,"x-qaira-request-trace":c.request_trace,"parameters":c.parameters or [],"responses":{"200":{"description":"Auto-discovered","content":{"application/json":{"schema":c.response_body or {"type":"object"}}}}}}
            if c.request_body: op["requestBody"]={"required":bool(c.request_body.get("required")),"content":{"application/json":{"schema":c.request_body}}}
            if c.auth.get("required"): op["security"]=[{"bearerAuth":[]}]
            paths.setdefault(c.path,{})[c.method.lower()]=op
        return {"openapi":"3.1.0","info":{"title":"QAira Semantic Compiler V58 API","version":"58.0.0"},"paths":paths,"components":{"securitySchemes":{"bearerAuth":{"type":"http","scheme":"bearer","bearerFormat":"JWT"}}}}
    def postman(self,contracts):
        items=[]
        for c in contracts:
            req={"method":c.method,"header":[{"key":k,"value":v} for k,v in headers(c.auth).items()],"url":{"raw":"{{baseUrl}}"+c.path,"host":["{{baseUrl}}"],"path":c.path.strip("/").split("/"),"query":[{"key":p.get("name"),"value":""} for p in (c.parameters or []) if p.get("in")=="query"]}}
            if c.request_body: req["body"]={"mode":"raw","raw":json.dumps(sample(c.request_body),indent=2),"options":{"raw":{"language":"json"}}}
            items.append({"name":c.api_id,"request":req})
        return {"info":{"name":"QAira V58 API Collection","schema":"https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},"variable":[{"key":"baseUrl","value":"http://localhost:3000"},{"key":"token","value":""}],"item":items}


class V53Governance:
    def __init__(self,cfg,store,learning,repo):
        self.cfg=cfg or {}
        self.store=store
        self.learning=Path(learning)
        self.repo=Path(repo)
        self.worked=[]
        self.failed=[]
        self.llm_suggested_worked=[]
    def _jsonl(self,name,item):
        try:
            p=self.store.out/"verbose"/name
            p.parent.mkdir(parents=True,exist_ok=True)
            with p.open("a",encoding="utf-8") as f:
                f.write(json.dumps(item,default=str)+"\n")
        except Exception:
            pass
    def stage(self,iteration,stage,status,outcome,evidence=None):
        item={"iteration":iteration,"stage":stage,"status":status,"outcome":outcome,"evidence":evidence or {},"ts":now_iso_v53()}
        self._jsonl("agent_stage_log.jsonl",item)
        if status=="success": self.worked.append(item)
        else: self.failed.append(item)
        review={"skipped":True,"reason":"llm_iteration_disabled","suggested_tasks":[]}
        if (self.cfg.get("llm_iteration") or {}).get("enabled",False):
            review={"deferred":True,"reason":"safe_runtime_records_prompt_only","suggested_tasks":[],"input":item}
        self.store.json(f"llm/stage_reviews/iteration_{iteration}_{safe_name_v53(stage)}.json",review)
    def score(self,summary):
        if not summary: return 0
        score=0; total=0
        for key,weight in [("bodyDetectionRate",20),("bodyFieldKnownRate",20)]:
            if key in summary:
                score += min(float(summary.get(key,0)),100)*weight/100
                total += weight
        score += 20 if summary.get("falsePositiveGETBodies",0)==0 else 0; total += 20
        actionable=float(summary.get("actionableUnresolvedRoutes",0) or 0)
        score += 20 if actionable==0 else max(0,20-actionable); total += 20
        attempts=float(summary.get("moduleResolutionAttempts",0) or 0)
        if attempts:
            score += min(100*float(summary.get("moduleResolutions",0))/max(attempts,1),100)*20/100
            total += 20
        return round((score/max(total,1))*100,2)
    def finalise(self,iteration,summary,extra=None):
        self.store.json("learning/worked_patterns.json",{"items":self.worked})
        self.store.json("learning/failed_patterns.json",{"items":self.failed})
        self.store.json("learning/llm_suggested_worked_patterns.json",{"items":self.llm_suggested_worked})
        try:
            self.learning.mkdir(parents=True,exist_ok=True)
            (self.learning/"worked_patterns.json").write_text(json.dumps({"items":self.worked},indent=2),encoding="utf-8")
            (self.learning/"failed_patterns.json").write_text(json.dumps({"items":self.failed},indent=2),encoding="utf-8")
            (self.learning/"llm_suggested_worked_patterns.json").write_text(json.dumps({"items":self.llm_suggested_worked},indent=2),encoding="utf-8")
        except Exception:
            pass
        threshold=(self.cfg.get("llm_results_analyser") or {}).get("threshold_percent",100)
        analysis={"score":self.score(summary),"threshold":threshold,"thresholdMatched":self.score(summary)>=threshold,"satisfied":self.score(summary)>=threshold,"what_worked":self.worked,"what_failed":self.failed,"next_steps":[]}
        if (self.cfg.get("llm_results_analyser") or {}).get("enabled",False):
            analysis["llm_deferred"]=True
            analysis["reason"]="safe_runtime_records_prompt_only"
        self.store.json(f"llm/results_analyser/iteration_{iteration}.json",analysis)
        self.store.json(f"llm/iterations/iteration_{iteration}.json",{"summary":summary,"extra":extra or {},"analysis":analysis})
        self._jsonl("results_analyser_log.jsonl",analysis)
        self._jsonl("iteration_log.jsonl",{"iteration":iteration,"analysis":analysis})
        patch_plan={"skipped":True,"reason":"code_generation_disabled","patches":[]}
        if (self.cfg.get("code_generation") or {}).get("enabled",False):
            patch_plan={"deferred":True,"reason":"safe_runtime_records_patch_request_only","patches":[]}
        self.store.json("llm/code_patch_plan.json",patch_plan)
        self.store.json("llm/final_llm_assessment.json",analysis)
        git_report={"enabled":bool((self.cfg.get("git_push") or {}).get("enabled",False)),"pushed":False}
        if not git_report["enabled"]: git_report["reason"]="git_push_disabled"
        else: git_report["reason"]="safe_runtime_no_git_push"
        self.store.json("git/code_push_report.json",git_report)
        self.store.json("git/pr_report.json",{"enabled":bool((self.cfg.get("pull_request") or {}).get("enabled",False)),"created":False,"reason":"safe_runtime_no_remote_pr_creation"})
        self._jsonl("code_pusher_log.jsonl",git_report)
        return analysis

def safe_name_v53(s):
    return re.sub(r"[^a-zA-Z0-9_.-]+","_",str(s))[:120]

def now_iso_v53():
    import datetime
    return datetime.datetime.utcnow().isoformat()+"Z"



class FrameworkNativeContractHarvesterV54:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
        self.report=[]
        self.contracts=[]
        self.comments=[]
        self.constraints=[]
    def run(self,fs):
        if not (self.cfg.get("framework_harvesting") or {}).get("enabled",True):
            return self.empty()
        self.harvest_openapi_files(fs)
        self.harvest_postman_files(fs)
        self.harvest_framework_metadata(fs)
        self.harvest_comments_and_docstrings(fs)
        self.harvest_validation_constraints(fs)
        result={"contracts":self.contracts,"comments":self.comments,"constraints":self.constraints,"report":self.report}
        self.store.json("harvest/framework_contracts.json",result)
        self.store.json("harvest/doc_comment_registry.json",{"items":self.comments})
        self.store.json("harvest/validation_constraints.json",{"items":self.constraints})
        self.store.json("diagnostics/framework_harvester_diagnostics.json",{"contracts":len(self.contracts),"comments":len(self.comments),"constraints":len(self.constraints),"report":self.report})
        return result
    def empty(self):
        return {"contracts":[],"comments":[],"constraints":[],"report":[{"skipped":True}]}
    def harvest_openapi_files(self,fs):
        pats=(self.cfg.get("framework_harvesting") or {}).get("openapi_file_patterns",["**/openapi*.json","**/swagger*.json","**/api-docs*.json"])
        count=0
        for pat in pats:
            for p in fs.src.glob(pat):
                if not p.is_file() or "node_modules" in str(p): continue
                try:
                    data=json.loads(p.read_text(encoding="utf-8",errors="ignore"))
                    if "openapi" in data or "swagger" in data or "paths" in data:
                        self.contracts.append({"source":"openapi_file","file":fs.rel(p),"content":data})
                        count+=1
                except Exception:
                    pass
        self.report.append({"harvester":"openapi_files","count":count})
    def harvest_postman_files(self,fs):
        pats=(self.cfg.get("framework_harvesting") or {}).get("postman_file_patterns",["**/*postman*.json","**/*collection*.json"])
        count=0
        for pat in pats:
            for p in fs.src.glob(pat):
                if not p.is_file() or "node_modules" in str(p): continue
                try:
                    data=json.loads(p.read_text(encoding="utf-8",errors="ignore"))
                    if "item" in data and "info" in data:
                        self.contracts.append({"source":"postman_file","file":fs.rel(p),"content":data})
                        count+=1
                except Exception:
                    pass
        self.report.append({"harvester":"postman_files","count":count})
    def harvest_framework_metadata(self,fs):
        count=0
        for p in fs.all_files():
            if p.suffix.lower() not in {".js",".jsx",".ts",".tsx",".py",".java",".cs"}: continue
            r=fs.rel(p); t=fs.read(p)
            patterns=[
                ("nestjs", r"@(Get|Post|Put|Patch|Delete)\s*\(\s*['\"`]([^'\"`]*)['\"`]"),
                ("fastapi", r"@(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]"),
                ("spring", r"@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)\s*(?:\(\s*['\"]([^'\"]+)['\"])?"),
                ("aspnet", r"\[(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete)(?:\(\s*['\"]([^'\"]+)['\"])?\]")
            ]
            for fw,pat in patterns:
                for m in re.finditer(pat,t,re.I):
                    self.contracts.append({"source":"framework_metadata","framework":fw,"file":r,"method":m.group(1),"path":m.group(2) if len(m.groups())>1 else "","line":line_no(t,m.start())})
                    count+=1
        self.report.append({"harvester":"framework_metadata","count":count})
    def harvest_comments_and_docstrings(self,fs):
        count=0
        for p in fs.all_files():
            if p.suffix.lower() not in {".js",".jsx",".ts",".tsx",".py",".java",".cs"}: continue
            r=fs.rel(p); t=fs.read(p)
            for m in re.finditer(r"/\*\*([\s\S]*?)\*/|///\s*(.*)|#\s*(.*)|\"\"\"([\s\S]*?)\"\"\"",t):
                text=" ".join([g for g in m.groups() if g]).strip()
                if text and len(text)>5:
                    self.comments.append({"file":r,"line":line_no(t,m.start()),"text":text[:1000]})
                    count+=1
        self.report.append({"harvester":"comments_docstrings","count":count})
    def harvest_validation_constraints(self,fs):
        count=0
        for p in fs.all_files():
            if p.suffix.lower() not in {".js",".jsx",".ts",".tsx",".py",".java",".cs"}: continue
            r=fs.rel(p); t=fs.read(p)
            constraint_patterns=[
                ("minLength", r"\.(?:min|minLength)\s*\(\s*(\d+)"),
                ("maxLength", r"\.(?:max|maxLength)\s*\(\s*(\d+)"),
                ("pattern", r"\.(?:regex|matches|pattern)\s*\(\s*[/\"']([^/\"']+)"),
                ("required", r"\.(?:required|nonempty)\s*\("),
                ("classValidatorMin", r"@Min\s*\(\s*(\d+)"),
                ("classValidatorMax", r"@Max\s*\(\s*(\d+)"),
                ("javaSize", r"@Size\s*\(([^)]*)\)"),
                ("pydanticField", r"Field\s*\(([^)]*)\)")
            ]
            for kind,pat in constraint_patterns:
                for m in re.finditer(pat,t):
                    self.constraints.append({"file":r,"line":line_no(t,m.start()),"kind":kind,"raw":m.group(0)[:300]})
                    count+=1
        self.report.append({"harvester":"validation_constraints","count":count})

class RequestRelationshipEngineV54:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
        self.graph={"nodes":[],"edges":[]}
        self.sequence=[]
        self.llm_prompts=[]
    def run(self,contracts):
        nodes=[]
        for c in contracts:
            resource=self.resource_key(c.path)
            node={"id":c.api_id,"method":c.method,"path":c.path,"resource":resource,"produces":self.produces(c),"consumes":self.consumes(c)}
            nodes.append(node)
        edges=[]
        by_resource={}
        for n in nodes:
            by_resource.setdefault(n["resource"],[]).append(n)
        order={"POST":1,"GET":2,"PUT":3,"PATCH":4,"DELETE":5}
        for res,items in by_resource.items():
            items=sorted(items,key=lambda x:order.get(x["method"],9))
            for a,b in zip(items,items[1:]):
                edges.append({"from":a["id"],"to":b["id"],"type":"CRUD_ORDER","confidence":0.82})
        # token/auth relation
        for a in nodes:
            if any(x in a["path"].lower() for x in ["login","token","auth"]):
                for b in nodes:
                    if a["id"]!=b["id"]:
                        edges.append({"from":a["id"],"to":b["id"],"type":"AUTH_PRECONDITION","confidence":0.75})
        self.graph={"nodes":nodes,"edges":edges}
        self.sequence=self.topologicalish(nodes,edges)
        conf=self.confidence(edges,nodes)
        if conf < (self.cfg.get("relationship_engine") or {}).get("llm_fallback_when_confidence_below",0.75):
            prompt={"reason":"low_sequence_confidence","confidence":conf,"nodes":nodes[:100],"edges":edges[:200]}
            self.llm_prompts.append(prompt)
            self.store.json("testing/llm_ordering_prompt.json",prompt)
        self.store.json("testing/request_dependency_graph.json",self.graph)
        self.store.json("testing/request_sequence_plan.json",{"confidence":conf,"sequence":self.sequence})
        return {"graph":self.graph,"sequence":self.sequence,"confidence":conf,"llmPrompts":self.llm_prompts}
    def resource_key(self,path):
        parts=[p for p in path.strip("/").split("/") if p and not p.startswith("{")]
        return "/".join(parts[:2]) if parts else "/"
    def produces(self,c):
        props=(c.response_body or {}).get("properties",{})
        return [k for k in props.keys() if k.lower().endswith("id") or k.lower()=="id"]
    def consumes(self,c):
        vals=[]
        for p in c.parameters or []:
            vals.append(p.get("name"))
        vals += list(((c.request_body or {}).get("properties") or {}).keys())
        return vals
    def confidence(self,edges,nodes):
        if not nodes: return 0
        return round(min(1.0,0.5+len(edges)/max(len(nodes)*3,1)),2)
    def topologicalish(self,nodes,edges):
        order={"POST":1,"GET":2,"PUT":3,"PATCH":4,"DELETE":5}
        return sorted(nodes,key=lambda n:(n["resource"],order.get(n["method"],9),n["path"]))

class TestGeneratorAgentV54:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
        self.test_cfg=cfg.get("test_generation") or {}
    def run(self,contracts,relationship):
        if not self.test_cfg.get("enabled",True):
            return {"skipped":True}
        types=set(self.test_cfg.get("types",["postman","curl"]))
        data_refs=self.build_data_refs(contracts)
        self.store.json("testing/test_data_references.json",data_refs)
        generated={}
        if "curl" in types: generated["curl"]=self.generate_curl(contracts)
        if "postman" in types: generated["postman"]="generated/openapi/postman existing + ordered metadata"
        if "qaira" in types: generated["qaira"]=self.generate_qaira(contracts,relationship)
        if "rest_assured" in types: generated["rest_assured"]=self.generate_rest_assured(contracts)
        if "playwright_api" in types: generated["playwright_api"]=self.generate_playwright(contracts)
        if "k6" in types: generated["k6"]=self.generate_k6(contracts)
        if "jmeter" in types: generated["jmeter"]=self.generate_jmeter(contracts)
        self.write_generated(generated)
        self.store.json("testing/test_generation_report.json",{"types":list(types),"generated":list(generated.keys())})
        return generated
    def ref_for(self,name,kind="data"):
        safe=re.sub(r"[^a-zA-Z0-9_]+","_",str(name)).strip("_") or "value"
        if kind=="vars": return "{{vars."+safe+"}}"
        if kind=="headers": return "{{headers."+safe+"}}"
        if kind=="query": return "{{query."+safe+"}}"
        return "{{data."+safe+"}}"
    def payload_for(self,c):
        body=(c.request_body or {}).get("properties") or {}
        return {k:self.ref_for(k,"data") for k in body.keys()}
    def params_for(self,c):
        out={}
        for p in c.parameters or []:
            loc=p.get("in")
            kind="vars" if loc=="path" else ("headers" if loc=="header" else "query")
            out[p["name"]]=self.ref_for(p["name"],kind)
        return out
    def build_data_refs(self,contracts):
        refs={}
        for c in contracts:
            refs[c.api_id]={"payload":self.payload_for(c),"params":self.params_for(c)}
        return refs
    def generate_curl(self,contracts):
        lines=["#!/usr/bin/env bash","set -euo pipefail",'BASE_URL="${BASE_URL:-http://localhost:3000}"']
        for c in contracts:
            path=re.sub(r"\{([^}]+)\}", r"${\\1}", c.path)
            payload=json.dumps(self.payload_for(c))
            if c.method in {"POST","PUT","PATCH"} and payload!="{}":
                lines.append(f"curl -X {c.method} \"$BASE_URL{path}\" -H 'Content-Type: application/json' -d '{payload}'")
            else:
                lines.append(f"curl -X {c.method} \"$BASE_URL{path}\"")
        return "\n".join(lines)+"\n"
    def generate_qaira(self,contracts,relationship):
        return json.dumps({"version":"v58","sequence":relationship.get("sequence",[]),"tests":[{"id":c.api_id,"method":c.method,"path":c.path,"payload":self.payload_for(c),"params":self.params_for(c)} for c in contracts]},indent=2)
    def generate_rest_assured(self,contracts):
        body=["import io.restassured.RestAssured;","public class GeneratedApiTests {","  String baseUrl = System.getProperty(\"baseUrl\", \"http://localhost:3000\");"]
        for i,c in enumerate(contracts[:200]):
            body.append(f"  @org.junit.jupiter.api.Test public void test_{i}() {{ RestAssured.given().baseUri(baseUrl).when().request(\"{c.method}\", \"{c.path}\").then().statusCode(org.hamcrest.Matchers.lessThan(500)); }}")
        body.append("}")
        return "\n".join(body)
    def generate_playwright(self,contracts):
        lines=["import { test, expect } from '@playwright/test';","const baseURL = process.env.BASE_URL || 'http://localhost:3000';"]
        for i,c in enumerate(contracts[:200]):
            lines.append(f"test('{c.method} {c.path}', async ({{ request }}) => {{ const res = await request.fetch(baseURL + '{c.path}', {{ method: '{c.method}' }}); expect(res.status()).toBeLessThan(500); }});")
        return "\n".join(lines)
    def generate_k6(self,contracts):
        lines=["import http from 'k6/http';","export default function () {","const baseURL = __ENV.BASE_URL || 'http://localhost:3000';"]
        for c in contracts[:200]:
            lines.append(f"http.request('{c.method}', baseURL + '{c.path}');")
        lines.append("}")
        return "\n".join(lines)
    def generate_jmeter(self,contracts):
        samples="".join([f'<HTTPSamplerProxy testname="{c.method} {c.path}" enabled="true"><stringProp name="HTTPSampler.method">{c.method}</stringProp><stringProp name="HTTPSampler.path">{c.path}</stringProp></HTTPSamplerProxy>' for c in contracts[:200]])
        return f'<?xml version="1.0" encoding="UTF-8"?><jmeterTestPlan version="1.2"><hashTree>{samples}</hashTree></jmeterTestPlan>'
    def write_generated(self,generated):
        mapping={"curl":"curl_requests.sh","qaira":"qaira_tests.json","rest_assured":"rest_assured_tests.java","playwright_api":"playwright_api_tests.spec.ts","k6":"k6_tests.js","jmeter":"jmeter_plan.jmx"}
        for k,v in generated.items():
            if k in mapping:
                p=self.store.out/"generated"/mapping[k]
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(v,encoding="utf-8")



class RepoCloneAgentV55:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
        self.report={}
    def run(self,current_source):
        repo_cfg=self.cfg.get("repo") or {}
        if not repo_cfg.get("enabled",False):
            self.report={"enabled":False,"sourceDir":str(current_source),"reason":"repo_clone_disabled"}
            self.store.json("repo/repo_clone_report.json",self.report)
            return Path(current_source)
        url=repo_cfg.get("url") or (self.cfg.get("git_push") or {}).get("repo_url","")
        clone_dir=Path(repo_cfg.get("clone_dir","/workspace/repo"))
        branch=repo_cfg.get("default_branch","develop")
        username=os.environ.get(repo_cfg.get("username_env","GIT_USERNAME"),"")
        token=os.environ.get(repo_cfg.get("token_env","GIT_TOKEN"),"")
        if not url:
            self.report={"enabled":True,"cloned":False,"reason":"repo_url_missing"}
            self.store.json("repo/repo_clone_report.json",self.report)
            return Path(current_source)
        if not username or not token:
            self.report={"enabled":True,"cloned":False,"reason":"git_credentials_env_missing","usernameEnv":repo_cfg.get("username_env","GIT_USERNAME"),"tokenEnv":repo_cfg.get("token_env","GIT_TOKEN")}
            self.store.json("repo/repo_clone_report.json",self.report)
            return Path(current_source)
        # Safe runtime does not execute remote clone by default. Record exact intended action.
        source_subdir=repo_cfg.get("source_subdir","")
        final_source=clone_dir/source_subdir if source_subdir else clone_dir
        self.report={"enabled":True,"cloned":False,"deferred":True,"reason":"safe_runtime_records_clone_plan_only","url":url,"branch":branch,"cloneDir":str(clone_dir),"finalSourceDir":str(final_source)}
        self.store.json("repo/repo_clone_report.json",self.report)
        return Path(current_source)

class StageLLMDecisionGateV55:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
    def decide(self,iteration,stage,status,outcome,evidence):
        prompt={
            "instruction":"Return JSON. Is the stage outcome correct? true/false only plus suggested deterministic tasks if false.",
            "iteration":iteration,
            "stage":stage,
            "status":status,
            "outcome":outcome,
            "evidence":evidence,
            "allowedTasks":(self.cfg.get("llm_iteration") or {}).get("allowed_task_types",[])
        }
        path=f"llm/stage_decision_prompts/iteration_{iteration}_{safe_name_v55(stage)}.json"
        self.store.json(path,prompt)
        if not ((self.cfg.get("llm") or {}).get("enabled") and (self.cfg.get("llm_iteration") or {}).get("enabled")):
            result={"llmEnabled":False,"accepted":status=="success","suggested_tasks":[],"reason":"llm_disabled"}
        else:
            result={"llmEnabled":True,"deferred":True,"accepted":status=="success","suggested_tasks":[],"reason":"safe_runtime_records_prompt_only"}
        self.store.json(f"llm/stage_reviews/iteration_{iteration}_{safe_name_v55(stage)}.json",result)
        return result

class SuggestedTaskExecutorV55:
    def __init__(self,cfg,store,learning):
        self.cfg=cfg or {}
        self.store=store
        self.learning=Path(learning)
        self.executed=[]
    def run(self,iteration,stage,tasks):
        allowed=set((self.cfg.get("llm_iteration") or {}).get("allowed_task_types",[]))
        for task in tasks or []:
            t=task.get("type")
            item={"iteration":iteration,"stage":stage,"task":task,"executed":False}
            if t not in allowed:
                item["reason"]="task_type_not_allowed"
            elif t=="add_pattern_to_learning":
                item["executed"]=True
                item["reason"]="pattern_recorded"
            else:
                item["executed"]=False
                item["reason"]="task_recorded_for_next_iteration"
            self.executed.append(item)
        self.store.json(f"llm/suggested_tasks/iteration_{iteration}_{safe_name_v55(stage)}.json",{"items":self.executed})
        return self.executed

class IterationMemoryStoreV55:
    def __init__(self,cfg,store,learning):
        self.cfg=cfg or {}
        self.store=store
        self.learning=Path(learning)
        self.worked=[]
        self.failed=[]
        self.llm_suggested_worked=[]
        self.iterations=[]
    def record_stage(self,iteration,stage,status,outcome,evidence,decision=None,tasks=None):
        item={"iteration":iteration,"stage":stage,"status":status,"outcome":outcome,"evidence":evidence or {},"decision":decision or {},"tasks":tasks or [],"ts":now_iso_v55()}
        if status=="success": self.worked.append(item)
        else: self.failed.append(item)
        if tasks:
            for t in tasks:
                if t.get("executed") and t.get("task",{}).get("worked"):
                    self.llm_suggested_worked.append({"iteration":iteration,"stage":stage,"task":t})
    def flush(self):
        self.store.json("learning/worked_patterns.json",{"items":self.worked})
        self.store.json("learning/failed_patterns.json",{"items":self.failed})
        self.store.json("learning/llm_suggested_worked_patterns.json",{"items":self.llm_suggested_worked})
        try:
            self.learning.mkdir(parents=True,exist_ok=True)
            (self.learning/"worked_patterns.json").write_text(json.dumps({"items":self.worked},indent=2),encoding="utf-8")
            (self.learning/"failed_patterns.json").write_text(json.dumps({"items":self.failed},indent=2),encoding="utf-8")
            (self.learning/"llm_suggested_worked_patterns.json").write_text(json.dumps({"items":self.llm_suggested_worked},indent=2),encoding="utf-8")
        except Exception:
            pass

class ActiveIterationRuntimeV55:
    def __init__(self,cfg,store,learning,repo):
        self.cfg=cfg or {}
        self.store=store
        self.learning=Path(learning)
        self.repo=Path(repo)
        self.gate=StageLLMDecisionGateV55(cfg,store)
        self.executor=SuggestedTaskExecutorV55(cfg,store,learning)
        self.memory=IterationMemoryStoreV55(cfg,store,learning)
    def log_jsonl(self,name,item):
        try:
            p=self.store.out/"verbose"/name
            p.parent.mkdir(parents=True,exist_ok=True)
            with p.open("a",encoding="utf-8") as f:
                f.write(json.dumps(item,default=str)+"\n")
        except Exception:
            pass
    def stage(self,iteration,stage,status,outcome,evidence=None):
        decision=self.gate.decide(iteration,stage,status,outcome,evidence or {})
        tasks=self.executor.run(iteration,stage,decision.get("suggested_tasks",[]))
        self.memory.record_stage(iteration,stage,status,outcome,evidence or {},decision,tasks)
        self.log_jsonl("agent_stage_log.jsonl",{"iteration":iteration,"stage":stage,"status":status,"outcome":outcome,"decision":decision,"tasks":tasks})
    def score(self,summary):
        if not summary: return 0
        total=0; score=0
        for key,weight in [("bodyDetectionRate",15),("bodyFieldKnownRate",15)]:
            if key in summary:
                score += min(float(summary.get(key,0)),100)*weight/100; total+=weight
        score += 15 if summary.get("falsePositiveGETBodies",0)==0 else 0; total+=15
        actionable=float(summary.get("actionableUnresolvedRoutes",0) or 0)
        score += 15 if actionable==0 else max(0,15-actionable); total+=15
        attempts=float(summary.get("moduleResolutionAttempts",0) or 0)
        if attempts:
            score += min(100*float(summary.get("moduleResolutions",0))/max(attempts,1),100)*15/100; total+=15
        score += min(float(summary.get("relationshipConfidence",0) or 0)*100,100)*10/100; total+=10
        score += 15 if summary.get("testsGenerated",False) else 0; total+=15
        return round(score/max(total,1)*100,2)
    def analyse_iteration(self,iteration,summary,output_index=None):
        threshold=(self.cfg.get("llm_results_analyser") or {}).get("threshold_percent",(self.cfg.get("llm_iteration") or {}).get("threshold_percent",100))
        score=self.score(summary)
        prompt={
            "instruction":"Analyse all agent outputs and return JSON: score, satisfied true/false, what_worked, what_failed, suggested_next_iteration_tasks.",
            "iteration":iteration,
            "summary":summary,
            "outputIndex":output_index or {},
            "worked":self.memory.worked,
            "failed":self.memory.failed,
            "llmSuggestedWorked":self.memory.llm_suggested_worked,
            "threshold":threshold
        }
        self.store.json(f"llm/results_analyser/prompts/iteration_{iteration}.json",prompt)
        if not ((self.cfg.get("llm") or {}).get("enabled") and (self.cfg.get("llm_results_analyser") or {}).get("enabled")):
            result={"llmEnabled":False,"score":score,"threshold":threshold,"satisfied":score>=threshold,"what_worked":self.memory.worked,"what_failed":self.memory.failed,"suggested_next_iteration_tasks":[]}
        else:
            result={"llmEnabled":True,"deferred":True,"score":score,"threshold":threshold,"satisfied":False,"suggested_next_iteration_tasks":[],"reason":"safe_runtime_records_prompt_only"}
        self.store.json(f"llm/results_analyser/iteration_{iteration}.json",result)
        self.store.json(f"iterations/iteration_{iteration}/iteration_result.json",{"summary":summary,"analysis":result})
        self.log_jsonl("results_analyser_log.jsonl",result)
        self.memory.flush()
        return result
    def finalise(self,analysis,final_tests_report=None):
        self.memory.flush()
        self.store.json("llm/final_llm_assessment.json",analysis)
        self.store.json("final/final_test_generation_report.json",final_tests_report or {})
        return analysis

class FinalTestGenerationAgentV55:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
    def run(self,contracts,relationship):
        # Reuse V54 generator if available.
        report={"enabled":True,"overridePrevious":(self.cfg.get("test_generation") or {}).get("final_override_previous",True),"types":(self.cfg.get("test_generation") or {}).get("types",[])}
        try:
            generated=TestGeneratorAgentV54(self.cfg,self.store).run(contracts,relationship or {})
            report["generated"]=list(generated.keys()) if isinstance(generated,dict) else []
        except Exception as e:
            report["error"]=str(e)
        self.store.json("final/final_test_generation_report.json",report)
        return report

class LLMCodeGenerationAgentV55:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
    def run(self,analysis,worked_patterns):
        cg=self.cfg.get("code_generation") or {}
        if not cg.get("enabled",False):
            result={"enabled":False,"reason":"code_generation_disabled","patches":[]}
        else:
            result={"enabled":True,"deferred":True,"reason":"safe_runtime_records_code_generation_request_only","analysis":analysis,"workedPatternsCount":len(worked_patterns),"patches":[]}
        self.store.json("llm/code_patch_plan.json",result)
        return result

class GitCommitPushAgentV55:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
    def run(self,patch_plan):
        git_cfg=self.cfg.get("git_push") or {}
        repo_cfg=self.cfg.get("repo") or {}
        repo_url=git_cfg.get("repo_url") or repo_cfg.get("url","")
        report={"enabled":bool(git_cfg.get("enabled",False)),"repoUrlConfigured":bool(repo_url),"targetBranch":git_cfg.get("target_branch",repo_cfg.get("default_branch","develop")),"committed":False,"pushed":False}
        if not git_cfg.get("enabled",False):
            report["reason"]="git_push_disabled"
        elif not repo_url:
            report["reason"]="repo_url_missing"
        elif not os.environ.get(git_cfg.get("username_env","GIT_USERNAME"),"") or not os.environ.get(git_cfg.get("token_env","GIT_TOKEN"),""):
            report["reason"]="git_credentials_env_missing"
        elif not git_cfg.get("push",False):
            report["reason"]="push_false"
        else:
            report["reason"]="safe_runtime_no_remote_push"
            report["intendedActions"]=["clone","checkout target branch","apply patches","commit","push","optional PR"]
        self.store.json("git/code_push_report.json",report)
        pr_cfg=self.cfg.get("pull_request") or {}
        self.store.json("git/pr_report.json",{"enabled":bool(pr_cfg.get("enabled",False)),"created":False,"reason":"safe_runtime_no_remote_pr_creation"})
        return report

def safe_name_v55(s):
    return re.sub(r"[^a-zA-Z0-9_.-]+","_",str(s))[:120]

def now_iso_v55():
    import datetime
    return datetime.datetime.utcnow().isoformat()+"Z"



class AgentConfidenceEngineV56:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
        self.items=[]
    def score_stage(self,stage,outcome):
        stage_l=stage.lower()
        score=0.5
        reason="default"
        try:
            if "route" in stage_l or "inlinehandler" in stage_l:
                routes=float(outcome.get("routes",0)); traces=float(outcome.get("requestTraces",0))
                score=0.99 if routes and traces>=routes*0.95 else 0.55
                reason="route_trace_ratio"
            elif "module" in stage_l or "importregistry" in stage_l:
                total=float(outcome.get("importsChecked",outcome.get("total",0)) or outcome.get("moduleResolutionAttempts",0) or 0)
                resolved=float(outcome.get("hydrated",0) or outcome.get("resolved",0) or outcome.get("moduleResolutions",0) or 0)
                score=round(resolved/max(total,1),2) if total else 0.35
                reason="module_resolution_rate"
            elif "dtoattachment" in stage_l:
                checked=float(outcome.get("checked",0) or 0); attached=float(outcome.get("attached",0) or 0)
                score=round(attached/max(checked,1),2) if checked else 0.30
                reason="dto_attachment_rate"
            elif "variablepropagation" in stage_l:
                found=float(outcome.get("propagations",0) or 0)
                score=0.85 if found>0 else 0.25
                reason="variable_propagations"
            elif "responsepropagation" in stage_l:
                found=float(outcome.get("propagations",0) or 0)
                score=0.85 if found>0 else 0.25
                reason="response_propagations"
            elif "testgenerator" in stage_l or "finaltest" in stage_l:
                generated=outcome.get("generated",[])
                score=0.95 if generated else 0.40
                reason="test_outputs"
            elif "diagnostic" in stage_l:
                score=0.90
                reason="diagnostic_classifier"
            else:
                score=0.80 if outcome else 0.30
        except Exception as e:
            score=0.20
            reason="score_exception:"+str(e)
        item={"stage":stage,"confidence":score,"reason":reason,"outcome":outcome}
        self.items.append(item)
        self.store.json("runtime/confidence_report.json",{"items":self.items})
        return item

class SelectiveLLMInvocationAgentV56:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
        self.items=[]
    def maybe_invoke(self,iteration,stage,status,confidence_item,evidence):
        inv_cfg=self.cfg.get("llm_invocation") or {}
        llm_cfg=self.cfg.get("llm") or {}
        threshold=float(inv_cfg.get("confidence_threshold",0.80))
        should=False
        reason=[]
        if status!="success" and inv_cfg.get("invoke_on_failure",True):
            should=True; reason.append("failure")
        if confidence_item.get("confidence",0)<threshold and inv_cfg.get("invoke_on_low_confidence",True):
            should=True; reason.append("low_confidence")
        if confidence_item.get("confidence",0)>=threshold and inv_cfg.get("invoke_on_high_confidence",False):
            should=True; reason.append("high_confidence_review")
        prompt={"iteration":iteration,"stage":stage,"status":status,"confidence":confidence_item,"evidence":evidence,"allowedTasks":inv_cfg.get("allowed_task_types",[]),"question":"Suggest deterministic next tasks only if needed."}
        result={"iteration":iteration,"stage":stage,"shouldInvoke":should,"reason":reason,"llmEnabled":bool(llm_cfg.get("enabled",False) and inv_cfg.get("enabled",False)),"suggested_tasks":[]}
        if should:
            self.store.json(f"llm/selective_prompts/iteration_{iteration}_{safe_name_v56(stage)}.json",prompt)
            if result["llmEnabled"]:
                result["deferred"]=True
                result["note"]="safe_runtime_records_prompt_only"
        self.items.append(result)
        self.store.json("runtime/selective_llm_invocation_report.json",{"items":self.items})
        try:
            if should:
                print(f"[Qaira][LLM-FAIL-OPEN] {stage} reason={reason} - prompt recorded, continuing", flush=True)
            else:
                print(f"[Qaira][LLM-SKIP] {stage} confidence={confidence_item.get('confidence')}", flush=True)
        except Exception:
            pass
        return result

class RuntimeExecutionManagerV56:
    def __init__(self,cfg,store,learning):
        self.cfg=cfg or {}
        self.store=store
        self.learning=Path(learning)
        self.conf=AgentConfidenceEngineV56(cfg,store)
        self.llm=SelectiveLLMInvocationAgentV56(cfg,store)
        self.worked=[]; self.failed=[]; self.iterations=[]
    def stage(self,iteration,stage,status,outcome,evidence=None):
        try:
            self.store.json(f"runtime/heartbeat_{safe_name_v56(stage)}.json",{"stage":stage,"status":"started"})
            print(f"[Qaira][START] {stage}", flush=True)
        except Exception:
            pass
        ci=self.conf.score_stage(stage,outcome or {})
        li=self.llm.maybe_invoke(iteration,stage,status,ci,evidence or {})
        item={"iteration":iteration,"stage":stage,"status":status,"outcome":outcome,"confidence":ci,"llm":li,"evidence":evidence or {}}
        if status=="success": self.worked.append(item)
        else: self.failed.append(item)
        self._jsonl("agent_stage_log.jsonl",item)
        self.store.json(f"runtime/iteration_{iteration}/stages/{safe_name_v56(stage)}.json",item)
        try:
            print(f"[Qaira][END] {stage} confidence={ci.get('confidence')} status={status}", flush=True)
        except Exception:
            pass
        return item
    def analyse(self,iteration,summary):
        threshold=float((self.cfg.get("runtime_execution") or {}).get("threshold_percent",100))
        score=self.score(summary)
        satisfied=score>=threshold
        result={"iteration":iteration,"score":score,"threshold":threshold,"satisfied":satisfied,"summary":summary,"worked":len(self.worked),"failed":len(self.failed)}
        self.iterations.append(result)
        self.store.json(f"runtime/iteration_{iteration}/iteration_summary.json",result)
        self.store.json("runtime/runtime_execution_report.json",{"iterations":self.iterations})
        self.store.json("learning/worked_patterns.json",{"items":self.worked})
        self.store.json("learning/failed_patterns.json",{"items":self.failed})
        self.store.json("learning/llm_suggested_worked_patterns.json",{"items":[]})
        try:
            self.learning.mkdir(parents=True,exist_ok=True)
            (self.learning/"worked_patterns.json").write_text(json.dumps({"items":self.worked},indent=2),encoding="utf-8")
            (self.learning/"failed_patterns.json").write_text(json.dumps({"items":self.failed},indent=2),encoding="utf-8")
        except Exception:
            pass
        self._jsonl("iteration_log.jsonl",result)
        return result
    def score(self,summary):
        score=0; total=0
        for key,weight in [("bodyDetectionRate",20),("bodyFieldKnownRate",20)]:
            if key in summary:
                score += min(float(summary.get(key,0)),100)*weight/100; total += weight
        score += 15 if summary.get("falsePositiveGETBodies",0)==0 else 0; total += 15
        actionable=float(summary.get("actionableUnresolvedRoutes",0) or 0)
        score += 15 if actionable==0 else max(0,15-actionable); total += 15
        attempts=float(summary.get("moduleResolutionAttempts",0) or 0)
        if attempts:
            score += min(100*float(summary.get("moduleResolutions",0))/max(attempts,1),100)*15/100; total += 15
        score += 15 if summary.get("testsGenerated",False) else 0; total += 15
        return round(score/max(total,1)*100,2)
    def _jsonl(self,name,item):
        try:
            p=self.store.out/"verbose"/name
            p.parent.mkdir(parents=True,exist_ok=True)
            with p.open("a",encoding="utf-8") as f:
                f.write(json.dumps(item,default=str)+"\n")
        except Exception:
            pass

class RealRepoAgentV56:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store
    def clone_if_enabled(self,current_source):
        repo=self.cfg.get("repo") or {}
        if not repo.get("enabled",False):
            report={"enabled":False,"sourceDir":str(current_source),"reason":"repo_clone_disabled"}
            self.store.json("git/repo_clone_report.json",report)
            return Path(current_source)
        url=repo.get("url",""); clone_dir=Path(repo.get("clone_dir","/workspace/repo"))
        branch=repo.get("default_branch","develop")
        execute=bool(repo.get("execute_git",False))
        user=os.environ.get(repo.get("username_env","GIT_USERNAME"),"")
        token=os.environ.get(repo.get("token_env","GIT_TOKEN"),"")
        report={"enabled":True,"urlConfigured":bool(url),"cloneDir":str(clone_dir),"branch":branch,"executeGit":execute,"cloned":False}
        if not url: report["reason"]="repo_url_missing"
        elif not user or not token: report["reason"]="git_credentials_env_missing"
        elif not execute: report["reason"]="execute_git_false_safe_plan_only"
        else:
            # Intentionally guarded. In real Docker runtime can enable execute_git; here record plan.
            report["reason"]="git_execution_guarded_in_generated_package"
            report["intendedCommand"]="git clone --branch <branch> <repo_url> <clone_dir>"
        self.store.json("git/repo_clone_report.json",report)
        return Path(current_source)

class VariablePropagationAgentV56:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store; self.report=[]
    def run(self,contracts):
        for c in contracts:
            raw=self.raw(c)
            aliases=set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:req|request)\.body",raw))
            aliases.update(["payload","body","data","input","dto"])
            fields=set()
            for a in aliases:
                fields.update(re.findall(r"\b"+re.escape(a)+r"\.([A-Za-z_$][\w$]*)",raw))
                for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*"+re.escape(a),raw):
                    for part in m.group(1).split(","):
                        name=part.strip().split(":")[0].strip()
                        if re.match(r"^[A-Za-z_$][\w$]*$",name): fields.add(name)
            if fields:
                self.report.append({"apiId":c.api_id,"path":c.path,"method":c.method,"aliases":sorted(aliases),"fields":sorted(fields)})
                if c.method in {"POST","PUT","PATCH"} and (not c.request_body or not c.request_body.get("properties")):
                    c.request_body={"type":"object","required":[],"properties":{f:{"type":"string","x-qaira-source":"variable_propagation"} for f in sorted(fields)}}
        self.store.json("propagation/variable_propagation_report.json",{"items":self.report,"propagations":len(self.report)})
        return {"propagations":len(self.report)}
    def raw(self,c):
        chunks=[]
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"): chunks.append(bi.get("rawHandler"))
        return "\n".join(chunks)

class ResponsePropagationAgentV56:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store; self.report=[]
    def run(self,contracts):
        for c in contracts:
            raw=self.raw(c)
            sends=re.findall(r"(?:reply|res|response)\.(?:send|json)\s*\(\s*([A-Za-z_$][\w$]*)",raw)
            returns=re.findall(r"return\s+([A-Za-z_$][\w$]*)",raw)
            vars_=list(dict.fromkeys(sends+returns))
            if vars_:
                self.report.append({"apiId":c.api_id,"path":c.path,"method":c.method,"responseVars":vars_})
                if not c.response_body or c.response_body.get("properties",{})=={"id":{"type":"string","x-qaira-source":"fallback_minimal"}}:
                    c.response_body={"type":"object","properties":{"id":{"type":"string","x-qaira-source":"response_propagation_placeholder"}}}
        self.store.json("propagation/response_propagation_report.json",{"items":self.report,"propagations":len(self.report)})
        return {"propagations":len(self.report)}
    def raw(self,c):
        chunks=[]
        for item in c.response_trace or []:
            if isinstance(item,dict):
                chunks.append(json.dumps(item))
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"): chunks.append(bi.get("rawHandler"))
        return "\n".join(chunks)

class DTOAttachmentAgentV56:
    def __init__(self,cfg,store,validation_registry):
        self.cfg=cfg or {}; self.store=store; self.validation=validation_registry or {"schemas":[]}; self.report=[]
    def run(self,contracts):
        checked=0; attached=0
        for c in contracts:
            if c.method in {"GET","HEAD","OPTIONS"}: continue
            if c.request_body and c.request_body.get("properties"): continue
            checked+=1
            schema=self.best_schema(c)
            if schema:
                c.request_body=schema.get("schema")
                attached+=1
                self.report.append({"apiId":c.api_id,"path":c.path,"method":c.method,"schema":schema.get("name"),"strategy":"dto_attachment_similarity"})
        self.store.json("propagation/dto_attachment_report.json",{"checked":checked,"attached":attached,"items":self.report})
        return {"checked":checked,"attached":attached}
    def best_schema(self,c):
        tokens=set(re.findall(r"[a-zA-Z0-9]+",c.path.lower()))
        best=None; best_score=0
        for s in self.validation.get("schemas",[]):
            name=s.get("name","").lower()
            stokens=set(re.findall(r"[a-zA-Z0-9]+",name))
            score=len(tokens & stokens)/max(len(tokens|stokens),1)
            if score>best_score:
                best_score=score; best=s
        min_sim=float((self.cfg.get("dto_attachment") or {}).get("min_similarity",0.72))
        return best if best and best_score>=min_sim else None

class FinalTestGenerationAgentV56:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store
    def run(self,contracts,relationship):
        report={"enabled":True,"generated":[]}
        try:
            generated=TestGeneratorAgentV54(self.cfg,self.store).run(contracts,relationship or {})
            report["generated"]=list(generated.keys()) if isinstance(generated,dict) else []
        except Exception as e:
            report["error"]=str(e)
        self.store.json("final/final_test_generation_report.json",report)
        return report

class GitCommitPushAgentV56:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store
    def run(self):
        git=self.cfg.get("git_push") or {}; repo=self.cfg.get("repo") or {}
        url=git.get("repo_url") or repo.get("url","")
        report={"enabled":bool(git.get("enabled",False)),"repoUrlConfigured":bool(url),"targetBranch":git.get("target_branch",repo.get("default_branch","develop")),"committed":False,"pushed":False}
        if not git.get("enabled",False): report["reason"]="git_push_disabled"
        elif not url: report["reason"]="repo_url_missing"
        elif not os.environ.get(git.get("username_env","GIT_USERNAME"),"") or not os.environ.get(git.get("token_env","GIT_TOKEN"),""): report["reason"]="git_credentials_env_missing"
        elif not git.get("execute_git",False) or not git.get("push",False): report["reason"]="execute_git_or_push_false"
        else: report["reason"]="git_execution_guarded_in_generated_package"
        self.store.json("git/code_push_report.json",report)
        self.store.json("git/pr_report.json",{"enabled":bool((self.cfg.get("pull_request") or {}).get("enabled",False)),"created":False,"reason":"safe_runtime_no_remote_pr_creation"})
        return report

def safe_name_v56(s):
    return re.sub(r"[^a-zA-Z0-9_.-]+","_",str(s))[:120]



class ImportHydrationAgentV57:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store; self.report=[]
        self.exts=[".js",".ts",".jsx",".tsx",".mjs",".cjs"]
        self.indexes=["index.js","index.ts","index.jsx","index.tsx"]
    def run(self,fs,import_registry):
        imports=import_registry.get("imports",[]) if isinstance(import_registry,dict) else []
        hydrated=0; checked=0
        for im in imports:
            checked+=1
            if im.get("resolvedFile"): continue
            module=im.get("module",""); file=im.get("file","")
            resolved=self.resolve_service_module(fs,file,module)
            if resolved:
                im["resolvedFile"]=resolved
                im["x-qaira-v57-hydrated"]=True
                hydrated+=1
            self.report.append({"file":file,"module":module,"resolvedFile":im.get("resolvedFile",""),"hydrated":bool(resolved),"attempts":getattr(self,"last_attempts",[])})
        result={"checked":checked,"hydrated":hydrated,"stillUnresolved":len([x for x in imports if not x.get("resolvedFile")]),"items":self.report}
        self.store.json("graph_completion/import_hydration_v57_report.json",result)
        return result
    def resolve_service_module(self,fs,from_file,module):
        self.last_attempts=[]
        if not module or not from_file: return ""
        base=(fs.src/from_file).parent
        candidates=[]
        if module.startswith("."):
            raw=(base/module).resolve()
            candidates.append(raw)
            for ext in self.exts:
                candidates.append(Path(str(raw)+ext))
            for idx in self.indexes:
                candidates.append(raw/idx)
        # service-specific brute force fallback by basename
        b=Path(module).name
        if b:
            for p in fs.src.rglob(b+"*"):
                if p.is_file() and p.suffix in self.exts and "node_modules" not in str(p):
                    candidates.append(p.resolve())
        for c in candidates:
            self.last_attempts.append(str(c))
            if c.exists() and c.is_file():
                try: return str(c.relative_to(fs.src)).replace("\\","/")
                except Exception: return str(c)
        return ""

class ServiceCallGraphAgentV57:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store
    def run(self,contracts,import_registry):
        imports=import_registry.get("imports",[]) if isinstance(import_registry,dict) else []
        by_file_local={}
        for im in imports:
            by_file_local[(im.get("file"),im.get("local"))]=im
        nodes=[]; edges=[]; unresolved=[]
        for c in contracts:
            route_file=self.route_file(c)
            raw=self.raw(c)
            nodes.append({"id":c.api_id,"type":"Route","path":c.path,"method":c.method,"file":route_file})
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*\(",raw):
                local,method=m.group(1),m.group(2)
                im=by_file_local.get((route_file,local))
                sid=f"service:{route_file}:{local}.{method}"
                nodes.append({"id":sid,"type":"ServiceCall","local":local,"method":method,"file":route_file,"resolvedFile":im.get("resolvedFile","") if im else ""})
                edges.append({"from":c.api_id,"to":sid,"type":"CALLS_SERVICE","confidence":0.85 if im and im.get("resolvedFile") else 0.45})
                if im and im.get("resolvedFile"):
                    impl=f"file:{im.get('resolvedFile')}:{method}"
                    nodes.append({"id":impl,"type":"ServiceImplementationCandidate","file":im.get("resolvedFile"),"method":method})
                    edges.append({"from":sid,"to":impl,"type":"RESOLVES_TO","confidence":0.82})
                else:
                    unresolved.append({"apiId":c.api_id,"local":local,"method":method,"routeFile":route_file})
        graph={"nodes":nodes,"edges":edges,"unresolved":unresolved,"edgeCount":len(edges)}
        self.store.json("graph_completion/service_call_graph_v57.json",graph)
        return graph
    def route_file(self,c):
        try: return (c.source_mappings.get("route") or [""])[0].split(":")[0]
        except Exception: return ""
    def raw(self,c):
        chunks=[]
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"): chunks.append(bi.get("rawHandler"))
        return "\n".join(chunks)

class ShapePropagationAgentV57:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store; self.report=[]
    def run(self,fs,contracts,service_graph):
        impl_nodes=[n for n in service_graph.get("nodes",[]) if n.get("type")=="ServiceImplementationCandidate"]
        impl_by_method={(n.get("file"),n.get("method")):n for n in impl_nodes}
        propagations=0
        for c in contracts:
            if c.method not in {"POST","PUT","PATCH"}: continue
            if c.request_body and c.request_body.get("properties"): continue
            raw=self.raw(c)
            aliases=self.aliases(raw)
            fields=set()
            for a in aliases:
                fields |= set(re.findall(r"\b"+re.escape(a)+r"\.([A-Za-z_$][\w$]*)",raw))
                fields |= self.destructured(raw,a)
            # service graph impl file field usage
            route_edges=[e for e in service_graph.get("edges",[]) if e.get("from")==c.api_id and e.get("type")=="CALLS_SERVICE"]
            for e in route_edges:
                service_node=next((n for n in service_graph.get("nodes",[]) if n.get("id")==e.get("to")),None)
                if not service_node: continue
                impl_file=service_node.get("resolvedFile",""); method=service_node.get("method","")
                if impl_file:
                    fields |= self.fields_from_impl(fs,impl_file,method)
            if fields:
                c.request_body={"type":"object","required":[],"properties":{f:{"type":"string","x-qaira-source":"shape_propagation_v57"} for f in sorted(fields)}}
                propagations+=1
                self.report.append({"apiId":c.api_id,"path":c.path,"method":c.method,"fields":sorted(fields)})
        result={"propagations":propagations,"items":self.report}
        self.store.json("graph_completion/shape_propagation_v57_report.json",result)
        return result
    def aliases(self,raw):
        out={"payload","body","data","input","dto","requestBody"}
        out |= set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:req|request)\.body",raw))
        return out
    def destructured(self,raw,alias):
        fields=set()
        for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*"+re.escape(alias),raw):
            for part in m.group(1).split(","):
                name=part.strip().split(":")[0].strip()
                if re.match(r"^[A-Za-z_$][\w$]*$",name): fields.add(name)
        return fields
    def fields_from_impl(self,fs,file,method):
        p=fs.src/file
        if not p.exists(): return set()
        t=fs.read(p)
        block=""
        m=re.search(r"(?:async\s+)?"+re.escape(method)+r"\s*[:=]?\s*(?:async\s*)?\(?([^)]*)\)?\s*=>?\s*\{([\s\S]{0,6000}?)\n?\}",t)
        if m: block=m.group(2)
        else:
            m=re.search(r"(?:async\s+)?"+re.escape(method)+r"\s*\(([^)]*)\)\s*\{([\s\S]{0,6000}?)\n?\}",t)
            if m: block=m.group(2)
        fields=set()
        for alias in ["payload","body","data","input","dto","requestBody"]:
            fields |= set(re.findall(r"\b"+alias+r"\.([A-Za-z_$][\w$]*)",block))
            fields |= self.destructured(block,alias)
        return fields
    def raw(self,c):
        chunks=[]
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"): chunks.append(bi.get("rawHandler"))
        return "\n".join(chunks)

class ReturnPropagationAgentV57:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}; self.store=store; self.report=[]
    def run(self,contracts,service_graph):
        count=0
        for c in contracts:
            raw=self.raw(c)
            vars_=set(re.findall(r"(?:reply|res|response)\.(?:send|json)\s*\(\s*([A-Za-z_$][\w$]*)",raw))
            vars_ |= set(re.findall(r"return\s+([A-Za-z_$][\w$]*)",raw))
            assigns=re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+([A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*)\(",raw)
            evidence=[{"var":v,"sourceCall":call} for v,call in assigns if v in vars_]
            if vars_ or evidence:
                count+=1
                self.report.append({"apiId":c.api_id,"path":c.path,"method":c.method,"responseVars":sorted(vars_),"evidence":evidence})
                if not c.response_body or not c.response_body.get("properties"):
                    c.response_body={"type":"object","properties":{"id":{"type":"string","x-qaira-source":"return_propagation_v57"}}}
        result={"propagations":count,"items":self.report}
        self.store.json("graph_completion/return_propagation_v57_report.json",result)
        return result
    def raw(self,c):
        chunks=[]
        for item in c.request_trace or []:
            if isinstance(item,dict):
                bi=item.get("bodyInfo") or {}
                if isinstance(bi,dict) and bi.get("rawHandler"): chunks.append(bi.get("rawHandler"))
        return "\n".join(chunks)

class DTOAttachmentAgentV57:
    def __init__(self,cfg,store,validation_registry):
        self.cfg=cfg or {}; self.store=store; self.validation=validation_registry or {"schemas":[]}; self.report=[]
    def run(self,contracts,service_graph):
        checked=0; attached=0
        schemas=self.validation.get("schemas",[])
        for c in contracts:
            if c.method in {"GET","HEAD","OPTIONS"}: continue
            if c.request_body and c.request_body.get("properties"): continue
            checked+=1
            candidates=self.names_from_graph(c,service_graph)
            schema=self.match_schema(candidates,schemas)
            if schema:
                c.request_body=schema.get("schema")
                attached+=1
                self.report.append({"apiId":c.api_id,"path":c.path,"method":c.method,"schema":schema.get("name"),"candidates":candidates})
        result={"checked":checked,"attached":attached,"items":self.report}
        self.store.json("graph_completion/dto_attachment_v57_report.json",result)
        return result
    def names_from_graph(self,c,graph):
        names=set(re.findall(r"[A-Za-z0-9]+",c.path))
        for e in graph.get("edges",[]):
            if e.get("from")==c.api_id:
                node=next((n for n in graph.get("nodes",[]) if n.get("id")==e.get("to")),None)
                if node:
                    names.add(node.get("method",""))
                    names.add(node.get("local",""))
        return [n for n in names if n]
    def match_schema(self,names,schemas):
        best=None; score=0
        nset=set([n.lower() for n in names if n])
        for s in schemas:
            st=set(re.findall(r"[a-zA-Z0-9]+",s.get("name","").lower()))
            sc=len(nset & st)/max(len(nset|st),1) if st else 0
            if sc>score:
                score=sc; best=s
        return best if best and score>=float((self.cfg.get("dto_attachment") or {}).get("min_similarity",0.70)) else None

class GraphCompletionSummaryAgentV57:
    def __init__(self,store):
        self.store=store
    def run(self,import_result,service_graph,shape_result,return_result,dto_result):
        summary={
            "importHydrated":import_result.get("hydrated",0),
            "serviceEdges":service_graph.get("edgeCount",0),
            "shapePropagations":shape_result.get("propagations",0),
            "returnPropagations":return_result.get("propagations",0),
            "dtoAttached":dto_result.get("attached",0),
            "dtoChecked":dto_result.get("checked",0)
        }
        self.store.json("graph_completion/graph_completion_summary.json",summary)
        return summary



class ConsoleProgressV58:
    def __init__(self,cfg,store):
        self.cfg=cfg or {}
        self.store=store
        self.enabled=bool((self.cfg.get("logging") or {}).get("verbose_console",True))
        self.path=self.store.out/"verbose"/"console_progress.log"
        self.path.parent.mkdir(parents=True,exist_ok=True)
    def log(self,msg,stage=None,level="INFO"):
        item={"ts":now_iso_v58(),"level":level,"stage":stage,"message":msg}
        line=f"[Qaira][{level}] {stage+': ' if stage else ''}{msg}"
        try:
            with self.path.open("a",encoding="utf-8") as f:
                f.write(json.dumps(item)+"\n")
        except Exception:
            pass
        if self.enabled:
            print(line, flush=True)
    def start(self,stage):
        self.log("started",stage,"START")
    def end(self,stage,outcome=None):
        self.log("completed "+(json.dumps(outcome,default=str)[:500] if outcome is not None else ""),stage,"END")
    def fail_open(self,stage,error):
        self.log("failed but continuing: "+str(error)[:500],stage,"FAIL-OPEN")

class FailOpenLLMGuardV58:
    def __init__(self,cfg,store,console):
        self.cfg=cfg or {}
        self.store=store
        self.console=console
        self.items=[]
    def guarded(self,stage,prompt,default=None):
        default=default or {"suggested_tasks":[]}
        llm_cfg=self.cfg.get("llm") or {}
        inv_cfg=self.cfg.get("llm_invocation") or {}
        if not (llm_cfg.get("enabled",False) and inv_cfg.get("enabled",False)):
            item={"stage":stage,"called":False,"reason":"llm_disabled","default":default}
            self.items.append(item)
            self.store.json("llm/fail_open_report.json",{"items":self.items})
            self.console.log("LLM skipped; deterministic flow continues",stage,"LLM-SKIP")
            return default
        # Safe generated runtime records prompt and fails open. This avoids hangs when network/API is unavailable.
        try:
            sid=sha(json.dumps(prompt,sort_keys=True,default=str))[:12]
            self.store.json(f"llm/selective_prompts/{safe_name_v58(stage)}_{sid}.json",prompt)
            item={"stage":stage,"called":True,"deferred":True,"reason":"safe_runtime_records_prompt_and_continues","timeoutSeconds":llm_cfg.get("timeout_seconds",20),"maxRetries":llm_cfg.get("max_retries",1),"default":default}
            self.items.append(item)
            self.store.json("llm/fail_open_report.json",{"items":self.items})
            self.console.log("LLM prompt recorded; continuing without blocking",stage,"LLM-FAIL-OPEN")
            return default
        except Exception as e:
            item={"stage":stage,"called":True,"error":str(e),"default":default}
            self.items.append(item)
            self.store.json("llm/fail_open_report.json",{"items":self.items})
            self.console.fail_open(stage,e)
            return default

def now_iso_v58():
    import datetime
    return datetime.datetime.utcnow().isoformat()+"Z"

def safe_name_v58(s):
    return re.sub(r"[^a-zA-Z0-9_.-]+","_",str(s))[:120]


class Orchestrator:
    def __init__(self,source,output,learning,changed_file,cfg,cfg_report):
        self.source=source.resolve(); self.output=output.resolve(); self.learning=learning.resolve()
        self.output.mkdir(parents=True,exist_ok=True); self.learning.mkdir(parents=True,exist_ok=True)
        changed=Path(changed_file).read_text(encoding="utf-8",errors="ignore").splitlines() if changed_file else []
        self.fs=FS(self.source,changed,int(cfg.get("parsing",{}).get("max_file_size_kb",4096)))
        self.cfg=cfg; self.log=Logger(self.output,cfg); self.store=Store(self.output,self.log)
        self.store.json("config/effective_config.json",cfg); self.store.json("config/config_validation_report.json",cfg_report)
        self.console_v58=ConsoleProgressV58(cfg,self.store)
        self.llm_guard_v58=FailOpenLLMGuardV58(cfg,self.store,self.console_v58)
        self.console_v58.log("QAira semantic compiler v58 initialized",None,"START")
        self.real_repo_agent_v56=RealRepoAgentV56(cfg,self.store)
        self.runtime_v56=RuntimeExecutionManagerV56(cfg,self.store,self.learning)
        self.repo_clone_agent=RepoCloneAgentV55(cfg,self.store)
        self.active_runtime=ActiveIterationRuntimeV55(cfg,self.store,self.learning,self.source)
        self.v53=V53Governance(cfg,self.store,self.learning,self.source)
    def run(self):
        self.repo_clone_agent.run(self.source)
        self.real_repo_agent_v56.clone_if_enabled(self.source)
        manifest,files=self.fs.fingerprint(); changed=[f["file"] for f in files if f["changed"]]
        self.runtime_v56.stage(1,"RepositoryFingerprint","success",{"files":len(files),"changed":len(changed)},{"sourceFiles":changed[:20]})
        self.store.json("repository/repository_manifest.json",manifest); self.store.json("repository/file_registry.json",files)
        framework_harvest=FrameworkNativeContractHarvesterV54(self.cfg,self.store).run(self.fs)
        self.runtime_v56.stage(1,"FrameworkNativeContractHarvesterV54","success",{"contracts":len(framework_harvest.get("contracts",[])),"comments":len(framework_harvest.get("comments",[])),"constraints":len(framework_harvest.get("constraints",[]))},{"sourceFiles":[]})
        orm_report,validation,orm_graph=OrmSinkAgent().run(self.fs)
        self.store.json("orm/orm_sink_report.json",orm_report); self.store.json("orm/validation_rule_inference.json",validation); self.store.json("graph/orm_graph.json",orm_graph)
        routes,graph,req_traces,res_traces,handler_report,body_report,parser_report=InlineHandlerCompiler().run(self.fs,self.cfg)
        self.runtime_v56.stage(1,"InlineHandlerCompiler","success",{"routes":len(routes),"requestTraces":len(req_traces)},{"sourceFiles":[r.get("file") for r in routes[:20]]})
        validation_registry,dto_registry,type_registry,validation_plugin_report=ValidationSchemaEngine(self.cfg).run(self.fs)
        validation_registry["typeRegistry"]=type_registry
        signature_registry=FunctionSignatureRegistry(self.cfg).run(self.fs)
        if not hasattr(self.fs,"_enterprise_module_resolver"):
            self.fs._enterprise_module_resolver=EnterpriseModuleResolverV51(self.cfg)
            self.fs._enterprise_module_resolver.initialize(self.fs)
        import_graph_resolver=ImportGraphResolver(self.cfg,self.fs._enterprise_module_resolver)
        import_registry=import_graph_resolver.run(self.fs)
        import_registry_hydrator=ImportRegistryHydratorV52(self.cfg,self.fs._enterprise_module_resolver)
        import_registry=import_registry_hydrator.hydrate(self.fs,import_registry)
        import_v57_result=ImportHydrationAgentV57(self.cfg,self.store).run(self.fs,import_registry)
        self.runtime_v56.stage(1,"ImportHydrationAgentV57","success" if import_v57_result.get("hydrated",0)>0 else "failure",import_v57_result,{"sourceFiles":[]})
        self.store.json("validation/validation_schema_registry.json",validation_registry)
        self.store.json("validation/dto_registry.json",dto_registry)
        self.store.json("validation/type_registry.json",type_registry)
        self.store.json("validation/function_signature_registry.json",signature_registry); self.store.json("validation/signature_extraction_diagnostics.json",{"files":signature_registry.get("diagnostics",[])})
        self.store.json("graph/import_graph.json",import_registry.get("graph",{}))
        self.store.json("graph/module_graph.json",import_registry.get("graph",{}))
        self.store.json("validation/import_registry.json",import_registry)
        self.store.json("validation/import_registry_hydrated.json",import_registry)
        self.store.json("validation/module_registry.json",import_registry)
        self.store.json("diagnostics/import_registry_hydration_audit.json",import_registry_hydrator.audit)
        self.store.json("diagnostics/resolved_path_propagation_audit.json",{"items":import_registry_hydrator.audit})
        self.store.json("diagnostics/v52_import_hydration_diagnostics.json",import_registry_hydrator.diagnostics)
        try:
            module_resolver=getattr(self.fs,"_enterprise_module_resolver",None)
            registry=module_resolver.registry if module_resolver else []
            audit=module_resolver.audit if module_resolver else {}
            trace=module_resolver.execution_trace if module_resolver else []
            comparison={
                "imports_discovered":len(import_registry.get("imports",[]))+len(import_registry.get("exports",[])),
                "imports_attempted":len(registry),
                "imports_resolved":len([x for x in registry if x.get("resolved")]),
                "imports_unresolved":len([x for x in registry if not x.get("resolved")])
            }
            self.store.json("validation/module_resolution_report.json",{"registry":registry,"audit":audit})
            self.store.json("validation/module_resolution_registry.json",{"items":registry})
            self.store.json("diagnostics/resolver_wiring_audit.json",audit)
            self.store.json("diagnostics/resolver_execution_trace.json",{"items":trace})
            self.store.json("diagnostics/import_pipeline_comparison.json",comparison)
            self.store.json("diagnostics/module_resolution_diagnostics.json",{"total":len(registry),"resolved":comparison["imports_resolved"],"unresolved":comparison["imports_unresolved"],"comparison":comparison})
        except Exception as e:
            self.store.json("diagnostics/module_resolution_diagnostics.json",{"error":str(e)})
        self.store.json("validation/validation_plugin_report.json",validation_plugin_report)
        enricher=SchemaEnricher(self.cfg,validation_registry,signature_registry,import_registry)
        schema_resolution=[]
        route_by_id={r["id"]:r for r in routes}
        for tr in req_traces:
            enriched,resolution=enricher.enrich_trace(route_by_id.get(tr.get("routeId"),{}),tr)
            tr["schema"]=enriched
            tr["trace"].append({"type":"v34_schema_enrichment","resolution":resolution})
            schema_resolution.append(resolution)
        self.store.json("validation/schema_resolution_report.json",schema_resolution); self.store.json("validation/dto_trace_report.json",enricher.dto_trace); self.store.json("validation/service_call_resolution_report.json",enricher.service_resolver.resolution_report); self.store.json("validation/type_resolution_report.json",enricher.type_engine.report); self.store.json("validation/object_shape_report.json",enricher.object_shape_analyzer.report)
        self.store.json("validation/object_shape_registry.json",{"shapes":enricher.object_shape_analyzer.shape_registry})
        self.store.json("validation/shape_registry.json",{"shapes":enricher.object_shape_analyzer.shape_registry})
        self.store.json("validation/shape_propagation_report.json",enricher.object_shape_analyzer.propagation_report)
        self.store.json("validation/function_return_propagation_report.json",[x for x in enricher.object_shape_analyzer.propagation_report if "builder" in x.get("type","")])
        self.store.json("validation/builder_shape_registry.json",{"builders":[s for s in enricher.object_shape_analyzer.shape_registry if "builder" in s.get("source","")]})
        self.store.json("validation/shape_merge_report.json",enricher.object_shape_analyzer.merge_report)
        self.store.json("validation/shape_confidence_report.json",enricher.object_shape_analyzer.confidence_report)
        self.store.json("graph/shape_graph.json",{"nodes":[{"id":s.get("shapeId"),"label":"Shape","properties":s} for s in enricher.object_shape_analyzer.shape_registry],"edges":[{"from":m.get("spread"),"to":m.get("target"),"type":"MERGES_INTO","properties":m} for m in enricher.object_shape_analyzer.merge_report]})
        self.store.json("ast/parser_capability_report.json",parser_report); self.store.json("graph/semantic_compiler_graph.json",graph); self.store.json("discovery/route_signals.json",routes)
        self.store.json("trace/request_tracebacks.json",req_traces); self.store.json("trace/response_tracebacks.json",res_traces)
        auth_graph,auth=AuthScopeCompiler().run(self.fs,routes); self.store.json("graph/auth_graph.json",auth_graph); self.store.json("auth/effective_auth_report.json",auth)
        request_context_engine=RequestContextEngine(self.cfg)
        contracts=ContractBuilder(request_context_engine).run(routes,req_traces,res_traces,auth)
        service_graph_v57=ServiceCallGraphAgentV57(self.cfg,self.store).run(contracts,import_registry)
        self.runtime_v56.stage(1,"ServiceCallGraphAgentV57","success" if service_graph_v57.get("edgeCount",0)>0 else "failure",{"edges":service_graph_v57.get("edgeCount",0),"unresolved":len(service_graph_v57.get("unresolved",[]))},{"sourceFiles":[]})
        shape_v57_result=ShapePropagationAgentV57(self.cfg,self.store).run(self.fs,contracts,service_graph_v57)
        self.runtime_v56.stage(1,"ShapePropagationAgentV57","success" if shape_v57_result.get("propagations",0)>0 else "failure",shape_v57_result,{"sourceFiles":[]})
        return_v57_result=ReturnPropagationAgentV57(self.cfg,self.store).run(contracts,service_graph_v57)
        self.runtime_v56.stage(1,"ReturnPropagationAgentV57","success" if return_v57_result.get("propagations",0)>0 else "failure",return_v57_result,{"sourceFiles":[]})
        dto_v57_result=DTOAttachmentAgentV57(self.cfg,self.store,validation_registry).run(contracts,service_graph_v57)
        self.runtime_v56.stage(1,"DTOAttachmentAgentV57","success" if dto_v57_result.get("attached",0)>0 else "failure",dto_v57_result,{"sourceFiles":[]})
        graph_completion_v57_summary=GraphCompletionSummaryAgentV57(self.store).run(locals().get("import_v57_result",{}),service_graph_v57,shape_v57_result,return_v57_result,dto_v57_result)
        vp_result=VariablePropagationAgentV56(self.cfg,self.store).run(contracts)
        self.runtime_v56.stage(1,"VariablePropagationAgentV56","success" if vp_result.get("propagations",0)>0 else "failure",vp_result,{"sourceFiles":[]})
        rp_result=ResponsePropagationAgentV56(self.cfg,self.store).run(contracts)
        self.runtime_v56.stage(1,"ResponsePropagationAgentV56","success" if rp_result.get("propagations",0)>0 else "failure",rp_result,{"sourceFiles":[]})
        dto_attach_result=DTOAttachmentAgentV56(self.cfg,self.store,validation_registry).run(contracts)
        self.runtime_v56.stage(1,"DTOAttachmentAgentV56","success" if dto_attach_result.get("attached",0)>0 else "failure",dto_attach_result,{"sourceFiles":[]})
        self.runtime_v56.stage(1,"ContractBuilder","success",{"contracts":len(contracts)},{"sourceFiles":[]})
        relationship_result=RequestRelationshipEngineV54(self.cfg,self.store).run(contracts)
        summary_relationship_confidence=relationship_result.get("confidence",0)
        self.runtime_v56.stage(1,"RequestRelationshipEngineV54","success",{"sequence":len(relationship_result.get("sequence",[])),"confidence":relationship_result.get("confidence")},{"sourceFiles":[]})
        self.runtime_v56.stage(1,"RequestRelationshipEngineV54","success",{"sequence":len(relationship_result.get("sequence",[])),"confidence":relationship_result.get("confidence")},{"sourceFiles":[]})
        test_generation_result=TestGeneratorAgentV54(self.cfg,self.store).run(contracts,relationship_result)
        self.runtime_v56.stage(1,"TestGeneratorAgentV54","success",{"generated":list(test_generation_result.keys()) if isinstance(test_generation_result,dict) else []},{"sourceFiles":[]})
        self.store.json("validation/request_context_report.json",request_context_engine.report)
        self.store.json("validation/query_param_registry.json",{"items":[r for r in request_context_engine.report if r.get("counts",{}).get("query",0)>0]})
        self.store.json("validation/path_param_registry.json",{"items":[r for r in request_context_engine.report if r.get("counts",{}).get("path",0)>0]})
        self.store.json("validation/header_registry.json",{"items":[r for r in request_context_engine.report if r.get("counts",{}).get("header",0)>0]})
        self.store.json("validation/cookie_registry.json",{"items":[r for r in request_context_engine.report if r.get("counts",{}).get("cookie",0)>0]})
        schema_attachment_resolver=SchemaAttachmentResolver(self.cfg,validation_registry)
        schema_attachment_summary=schema_attachment_resolver.run(contracts,self.fs)
        self.store.json("validation/schema_attachment_report.json",schema_attachment_summary)
        self.store.json("validation/route_schema_link_report.json",schema_attachment_resolver.report)
        self.store.json("validation/schema_attachment_registry.json",{"items":schema_attachment_resolver.registry})
        self.store.json("diagnostics/schema_attachment_diagnostics.json",schema_attachment_resolver.diagnostics)
        unresolved_investigator=UnresolvedRouteInvestigator(self.cfg,validation_registry,signature_registry,import_registry)
        unresolved_summary,recovered_contracts=unresolved_investigator.run(contracts,self.fs)
        self.runtime_v56.stage(1,"UnresolvedRouteInvestigator","success",unresolved_summary,{"sourceFiles":[]})
        self.store.json("validation/unresolved_routes.json",{"items":[safe_json(c) for c in contracts if c.method not in {"GET","HEAD","OPTIONS"} and (not c.request_body or not (c.request_body.get("properties") or {}))]})
        self.store.json("validation/unresolved_route_investigation_report.json",unresolved_summary)
        self.store.json("validation/validation_chain_report.json",unresolved_investigator.validation_resolver.report)
        self.store.json("validation/service_input_usage_report.json",unresolved_investigator.service_usage_resolver.report)
        self.store.json("validation/recovered_unresolved_contracts.json",recovered_contracts)
        self.store.json("diagnostics/unresolved_route_diagnostics.json",unresolved_summary)
        diagnostic_classifier=DiagnosticClassifier(self.cfg)
        route_classification_report=diagnostic_classifier.run(contracts)
        self.runtime_v56.stage(1,"DiagnosticClassifier","success",route_classification_report.get("summary",{}),{"sourceFiles":[]})
        next_action_report=NextActionReportBuilder().run(route_classification_report)
        self.store.json("diagnostics/route_classification_report.json",route_classification_report)
        self.store.json("diagnostics/unresolved_classification_report.json",route_classification_report)
        self.store.json("diagnostics/real_unresolved_payload_routes.json",{"items":route_classification_report.get("buckets",{}).get("real_unresolved",[])})
        self.store.json("diagnostics/next_action_report.json",next_action_report)
        export_resolver_v49=ExportResolverV49(self.cfg)
        service_implementation_registry=export_resolver_v49.build_registry(self.fs)
        import_aware_service_resolver=ImportAwareServiceResolverV49(self.cfg,import_registry,service_implementation_registry)
        actionable_recovery=ActionableRecoveryEngineV48(self.cfg,validation_registry,signature_registry,import_registry,import_aware_service_resolver)
        actionable_recovery_report,recovered_actionable_contracts=actionable_recovery.run(contracts,route_classification_report,self.fs)
        self.runtime_v56.stage(1,"ActionableRecoveryEngineV48","success" if actionable_recovery_report.get("recovered",0)>0 else "failure",actionable_recovery_report,{"sourceFiles":[]})
        self.store.json("validation/export_resolution_report.json",export_resolver_v49.report)
        self.store.json("validation/service_implementation_registry.json",{"items":export_resolver_v49.registry})
        self.store.json("validation/import_aware_service_resolution_report.json",import_aware_service_resolver.report)
        self.store.json("diagnostics/v49_service_resolution_diagnostics.json",{"resolutions":import_aware_service_resolver.report,"implementations":len(export_resolver_v49.registry)})
        self.store.json("validation/validation_wrapper_resolution_report.json",actionable_recovery.validation_wrapper.report)
        self.store.json("validation/service_semantic_trace_report.json",actionable_recovery.service_tracer.report)
        self.store.json("validation/actionable_recovery_report.json",actionable_recovery_report)
        self.store.json("validation/recovered_actionable_contracts.json",recovered_actionable_contracts)
        self.store.json("diagnostics/v48_recovery_diagnostics.json",actionable_recovery_report)

        self.store.json("validation/route_classification_registry.json",route_classification_report)
        self.store.json("validation/real_unresolved_routes.json",{"items":route_classification_report.get("buckets",{}).get("real_unresolved",[])})


        self.store.json("discovery/unified_api_contracts.json",contracts)
        handler_diag,body_diag,body_detail=DiagnosticsAgent().run(contracts,handler_report,body_report)
        self.store.json("diagnostics/handler_detection_report.json",handler_diag); self.store.json("diagnostics/body_detection_report.json",body_diag); self.store.json("diagnostics/body_detection_detail.json",body_detail); shape_diag={"strategies":{s.get("strategy"):sum(1 for x in schema_resolution if x.get("strategy")==s.get("strategy")) for s in schema_resolution},"routes":schema_resolution,"serviceResolutionCount":len(enricher.service_resolver.resolution_report),"objectShapesFound":len(enricher.object_shape_analyzer.shape_registry),"shapePropagations":len(enricher.object_shape_analyzer.propagation_report),"functionReturnPropagations":len([x for x in enricher.object_shape_analyzer.propagation_report if "builder" in x.get("type","")]),"shapeMerges":len(enricher.object_shape_analyzer.merge_report)}
        self.store.json("diagnostics/schema_resolution_diagnostics.json",shape_diag)
        self.store.json("diagnostics/shape_resolution_diagnostics.json",shape_diag)
        self.store.json("diagnostics/request_context_diagnostics.json",{"routes":request_context_engine.report,"totals":{"body":sum(r.get("counts",{}).get("body",0) for r in request_context_engine.report),"query":sum(r.get("counts",{}).get("query",0) for r in request_context_engine.report),"path":sum(r.get("counts",{}).get("path",0) for r in request_context_engine.report),"header":sum(r.get("counts",{}).get("header",0) for r in request_context_engine.report),"cookie":sum(r.get("counts",{}).get("cookie",0) for r in request_context_engine.report)}})
        impact,drift=DriftImpactAgent().run(self.learning,contracts,changed); self.store.json("impact/change_impact_report.json",impact); self.store.json("impact/contract_drift_report.json",drift)
        failures,slices,llm_requests,effectiveness=LLMFallbackBundle().run(self.fs,self.learning,contracts,drift,self.cfg)
        self.store.json("llm/semantic_slices.json",slices); self.store.json("llm/llm_fallback_requests.json",llm_requests); self.store.json("llm/llm_effectiveness.json",effectiveness)
        self.store.json("learning/object-shapes/patterns.json",{"patterns":list(enricher.object_shape_analyzer.learning_patterns.values())})
        try:
            (self.learning/"object-shapes").mkdir(parents=True,exist_ok=True)
            (self.learning/"object-shapes"/"patterns.json").write_text(json.dumps({"patterns":list(enricher.object_shape_analyzer.learning_patterns.values())},indent=2),encoding="utf-8")
        except Exception:
            pass
        ArtifactGenerator().run(contracts,self.store)
        body_expected=len([c for c in contracts if c.method in {"POST","PUT","PATCH"}])
        body_detected=len([c for c in contracts if c.method in {"POST","PUT","PATCH"} and c.request_body])
        body_fields_known=len([c for c in contracts if c.method in {"POST","PUT","PATCH"} and c.request_body and (c.request_body.get("properties") or {})])
        summary={"apiContracts":len(contracts),"bodyExpected":body_expected,"bodyDetected":body_detected,"bodyFieldsKnown":body_fields_known,"bodyDetectionRate":round((body_detected/body_expected)*100,2) if body_expected else 100,"bodyFieldKnownRate":round((body_fields_known/body_expected)*100,2) if body_expected else 100,"validationSchemasDiscovered":len(validation_registry.get("schemas",[])),"functionSignaturesDiscovered":len(signature_registry.get("signatures",[])),"typedFunctionSignatures":len([s for s in signature_registry.get("signatures",[]) if any(p.get("type") for p in s.get("params",[]))]),"typesDiscovered":len(type_registry.get("types",[])),"typeResolutions":len([x for x in enricher.type_engine.report if x.get("status","").startswith("resolved")]),"importsDiscovered":len(import_registry.get("imports",[])),"exportsDiscovered":len(import_registry.get("exports",[])),"commonJsImports":len([i for i in import_registry.get("imports",[]) if str(i.get("kind","")).startswith("commonjs")]),"commonJsExports":len([e for e in import_registry.get("exports",[]) if str(e.get("kind","")).startswith("commonjs")]),"serviceResolutions":len(enricher.service_resolver.resolution_report),"objectShapesFound":len(enricher.object_shape_analyzer.shape_registry),"shapePropagations":len(enricher.object_shape_analyzer.propagation_report),"functionReturnPropagations":len([x for x in enricher.object_shape_analyzer.propagation_report if "builder" in x.get("type","")]),"shapeMerges":len(enricher.object_shape_analyzer.merge_report),"falsePositiveGETBodies":len([c for c in contracts if c.method in {"GET","HEAD","OPTIONS"} and c.request_body]),"schemaAttachmentsResolved":schema_attachment_resolver.diagnostics.get("schemasResolved",0),"schemaAttachmentsFound":schema_attachment_resolver.diagnostics.get("attachmentsFound",0),"unresolvedRecovered":unresolved_summary.get("recovered",0),"unresolvedAfterInvestigation":unresolved_summary.get("unresolvedAfter",0),"bodyNotExpectedRoutes":diagnostic_classifier.summary.get("body_not_expected",0),"realUnresolvedPayloadRoutes":diagnostic_classifier.summary.get("real_unresolved",0),"actionableUnresolvedRoutes":diagnostic_classifier.summary.get("actionableUnresolvedRoutes",0),"v52HydratedImports":import_registry_hydrator.diagnostics.get("hydrated",0),"v52StillUnresolvedImports":import_registry_hydrator.diagnostics.get("stillUnresolved",0),"moduleResolutions":len([x for x in (getattr(self.fs,"_enterprise_module_resolver",None).registry if getattr(self.fs,"_enterprise_module_resolver",None) else []) if x.get("resolved")]),"moduleResolutionAttempts":len((getattr(self.fs,"_enterprise_module_resolver",None).registry if getattr(self.fs,"_enterprise_module_resolver",None) else [])),"v49ServiceImplementations":len(export_resolver_v49.registry),"v49ImportAwareResolutions":len([x for x in import_aware_service_resolver.report if x.get("resolved")]),"v48ActionableRecovered":actionable_recovery_report.get("recovered",0),"v48ActionableUnrecovered":actionable_recovery_report.get("unrecovered",0),"queryParamsDiscovered":sum(r.get("counts",{}).get("query",0) for r in request_context_engine.report),"pathParamsDiscovered":sum(r.get("counts",{}).get("path",0) for r in request_context_engine.report),"headersDiscovered":sum(r.get("counts",{}).get("header",0) for r in request_context_engine.report),"cookiesDiscovered":sum(r.get("counts",{}).get("cookie",0) for r in request_context_engine.report),"treeSitterAvailable":TREE_SITTER_AVAILABLE,"llmFallbackPrepared":len(llm_requests)}
        
        try:
            summary["v57ImportHydrated"]=graph_completion_v57_summary.get("importHydrated",0)
            summary["v57ServiceEdges"]=graph_completion_v57_summary.get("serviceEdges",0)
            summary["v57ShapePropagations"]=graph_completion_v57_summary.get("shapePropagations",0)
            summary["v57ReturnPropagations"]=graph_completion_v57_summary.get("returnPropagations",0)
            summary["v57DtoAttached"]=graph_completion_v57_summary.get("dtoAttached",0)
        except Exception:
            pass
        self.store.json("summary/scan_summary.json",summary)
        self.console_v58.log("scan summary written", "Summary", "END")
        try:
            summary["testsGenerated"]=bool(locals().get("test_generation_result",{}))
        except Exception:
            pass
        runtime_analysis_v56=self.runtime_v56.analyse(1,summary)
        final_tests_v56=FinalTestGenerationAgentV56(self.cfg,self.store).run(contracts,locals().get("relationship_result",{}))
        GitCommitPushAgentV56(self.cfg,self.store).run()
        try:
            summary["relationshipConfidence"]=locals().get("summary_relationship_confidence",0)
            summary["testsGenerated"]=bool(locals().get("test_generation_result",{}))
        except Exception:
            pass
        final_analysis=self.active_runtime.analyse_iteration(1,summary,{"outputRoot":str(self.output)})
        final_tests_report=FinalTestGenerationAgentV55(self.cfg,self.store).run(contracts,locals().get("relationship_result",{}))
        self.active_runtime.finalise(final_analysis,final_tests_report)
        patch_plan=LLMCodeGenerationAgentV55(self.cfg,self.store).run(final_analysis,self.active_runtime.memory.worked+self.active_runtime.memory.llm_suggested_worked)
        GitCommitPushAgentV55(self.cfg,self.store).run(patch_plan)
        self.active_runtime.analyse_iteration(1,summary,{"route_classification":route_classification_report if "route_classification_report" in locals() else {},"actionable_recovery":actionable_recovery_report if "actionable_recovery_report" in locals() else {}})
        self.store.text("summary/final_report.md",f"""# QAira Semantic Compiler Platform V32 Report

- API contracts: **{summary['apiContracts']}**
- Body expected: **{summary['bodyExpected']}**
- Body detected: **{summary['bodyDetected']}**
- Body detection rate: **{summary['bodyDetectionRate']}%**
- Body fields known: **{summary['bodyFieldsKnown']}**
- Body field known rate: **{summary['bodyFieldKnownRate']}%**
- Validation schemas discovered: **{summary['validationSchemasDiscovered']}**
- Function signatures discovered: **{summary['functionSignaturesDiscovered']}**
- Typed function signatures: **{summary['typedFunctionSignatures']}**
- Types discovered: **{summary['typesDiscovered']}**
- Type resolutions: **{summary['typeResolutions']}**
- Imports discovered: **{summary['importsDiscovered']}**
- Exports discovered: **{summary['exportsDiscovered']}**
- CommonJS imports: **{summary['commonJsImports']}**
- CommonJS exports: **{summary['commonJsExports']}**
- Service resolutions: **{summary['serviceResolutions']}**
- Object shapes found: **{summary['objectShapesFound']}**
- Shape propagations: **{summary['shapePropagations']}**
- Function return propagations: **{summary['functionReturnPropagations']}**
- Shape merges: **{summary['shapeMerges']}**
- False-positive GET bodies: **{summary['falsePositiveGETBodies']}**
- Schema attachments found: **{summary['schemaAttachmentsFound']}**
- Schema attachments resolved: **{summary['schemaAttachmentsResolved']}**
- Unresolved routes recovered: **{summary['unresolvedRecovered']}**
- Unresolved after investigation: **{summary['unresolvedAfterInvestigation']}**
- Body-not-expected routes: **{summary['bodyNotExpectedRoutes']}**
- Real unresolved payload routes: **{summary['realUnresolvedPayloadRoutes']}**
- Actionable unresolved routes: **{summary['actionableUnresolvedRoutes']}**
- V52 hydrated imports: **{summary['v52HydratedImports']}**
- V52 still unresolved imports: **{summary['v52StillUnresolvedImports']}**
- Module resolutions: **{summary['moduleResolutions']} / {summary['moduleResolutionAttempts']}**
- V49 service implementations indexed: **{summary['v49ServiceImplementations']}**
- V49 import-aware service resolutions: **{summary['v49ImportAwareResolutions']}**
- V48 actionable recovered: **{summary['v48ActionableRecovered']}**
- V48 actionable unrecovered: **{summary['v48ActionableUnrecovered']}**
- Query params discovered: **{summary['queryParamsDiscovered']}**
- Path params discovered: **{summary['pathParamsDiscovered']}**
- Headers discovered: **{summary['headersDiscovered']}**
- Cookies discovered: **{summary['cookiesDiscovered']}**
- LLM fallback requests prepared: **{summary['llmFallbackPrepared']}**

## Read first

- `diagnostics/body_detection_report.json`
- `diagnostics/handler_detection_report.json`
- `validation/validation_schema_registry.json`
- `validation/schema_resolution_report.json`
- `validation/function_signature_registry.json`
- `validation/signature_extraction_diagnostics.json`
- `validation/type_registry.json`
- `validation/type_resolution_report.json`
- `validation/object_shape_report.json`
- `validation/object_shape_registry.json`
- `validation/shape_registry.json`
- `validation/shape_propagation_report.json`
- `validation/function_return_propagation_report.json`
- `validation/builder_shape_registry.json`
- `validation/shape_merge_report.json`
- `validation/shape_confidence_report.json`
- `diagnostics/shape_resolution_diagnostics.json`
- `diagnostics/request_context_diagnostics.json`
- `validation/request_context_report.json`
- `validation/schema_attachment_report.json`
- `validation/route_schema_link_report.json`
- `validation/schema_attachment_registry.json`
- `diagnostics/schema_attachment_diagnostics.json`
- `validation/unresolved_routes.json`
- `validation/unresolved_route_investigation_report.json`
- `validation/validation_chain_report.json`
- `validation/service_input_usage_report.json`
- `validation/recovered_unresolved_contracts.json`
- `diagnostics/unresolved_route_diagnostics.json`
- `diagnostics/route_classification_report.json`
- `diagnostics/unresolved_classification_report.json`
- `diagnostics/real_unresolved_payload_routes.json`
- `diagnostics/next_action_report.json`
- `validation/validation_wrapper_resolution_report.json`
- `validation/service_semantic_trace_report.json`
- `validation/actionable_recovery_report.json`
- `validation/recovered_actionable_contracts.json`
- `diagnostics/v48_recovery_diagnostics.json`
- `validation/import_aware_service_resolution_report.json`
- `validation/export_resolution_report.json`
- `validation/service_implementation_registry.json`
- `diagnostics/v49_service_resolution_diagnostics.json`
- `validation/module_resolution_report.json`
- `validation/module_resolution_registry.json`
- `diagnostics/module_resolution_diagnostics.json`
- `diagnostics/resolver_wiring_audit.json`
- `diagnostics/resolver_execution_trace.json`
- `diagnostics/import_pipeline_comparison.json`
- `diagnostics/import_registry_hydration_audit.json`
- `diagnostics/resolved_path_propagation_audit.json`
- `diagnostics/v52_import_hydration_diagnostics.json`
- `validation/import_registry_hydrated.json`
- `llm/iterations/iteration_1.json`
- `llm/stage_reviews/*.json`
- `llm/results_analyser/iteration_1.json`
- `learning/worked_patterns.json`
- `learning/failed_patterns.json`
- `git/code_push_report.json`
- `runtime/runtime_execution_report.json`
- `runtime/confidence_report.json`
- `runtime/selective_llm_invocation_report.json`
- `propagation/variable_propagation_report.json`
- `propagation/response_propagation_report.json`
- `propagation/dto_attachment_report.json`
- `graph_completion/import_hydration_v57_report.json`
- `graph_completion/service_call_graph_v57.json`
- `graph_completion/shape_propagation_v57_report.json`
- `graph_completion/return_propagation_v57_report.json`
- `graph_completion/dto_attachment_v57_report.json`
- `graph_completion/graph_completion_summary.json`
- `repo/repo_clone_report.json`
- `final/final_test_generation_report.json`
- `llm/stage_decision_prompts/*.json`
- `validation/route_classification_registry.json`
- `validation/real_unresolved_routes.json`
- `validation/query_param_registry.json`
- `validation/path_param_registry.json`
- `validation/header_registry.json`
- `validation/cookie_registry.json`
- `learning/object-shapes/patterns.json`
- `validation/dto_trace_report.json`
- `validation/service_call_resolution_report.json`
- `validation/import_registry.json`
- `validation/module_registry.json`
- `graph/module_graph.json`
- `graph/import_graph.json`
- `diagnostics/schema_resolution_diagnostics.json`
- `trace/request_tracebacks.json`
- `generated/openapi.json`
""")
        self.log.info("orchestrator","scan completed",summary=summary)
        return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--learning",required=True)
    ap.add_argument("--config")
    ap.add_argument("--changed-files")
    args=ap.parse_args()
    cfg,cfg_report=load_config(Path(args.config) if args.config else None)
    return Orchestrator(Path(args.source),Path(args.output),Path(args.learning),args.changed_files,cfg,cfg_report).run()

if __name__=="__main__":
    raise SystemExit(main())
