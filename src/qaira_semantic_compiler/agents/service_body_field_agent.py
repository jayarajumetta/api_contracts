from qaira_semantic_compiler.core.context import AgentResult
import re

class ServiceBodyFieldAgent:
    name="ServiceBodyFieldAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        idx=self.ctx.state["index"]
        service_edges=self.ctx.state.get("serviceEdges",[])
        patterns=[]
        by_route={}

        for edge in service_edges:
            route_id=edge.get("from")
            service_file=edge.get("toFile")
            method=edge.get("method")
            if not service_file or not method:
                continue
            try:
                text=idx.read(service_file)
            except Exception:
                continue

            block=self.extract_method_block(text, method)
            if not block:
                continue

            fields=self.extract_body_fields(block)
            if fields:
                item={
                    "routeId":route_id,
                    "serviceFile":service_file,
                    "method":method,
                    "fields":sorted(fields),
                    "confidence":0.78
                }
                patterns.append(item)
                by_route.setdefault(route_id,set()).update(fields)

        self.ctx.state["serviceBodyFieldsByRoute"]={k:sorted(v) for k,v in by_route.items()}
        self.ctx.write_json("patterns/service_body_field_patterns.json", {
            "count":len(patterns),
            "routes":len(by_route),
            "items":patterns
        })
        return AgentResult(
            self.name,
            "success" if patterns else "failed_open",
            0.8 if patterns else 0.25,
            {"patterns":len(patterns),"routes":len(by_route)},
            {}
        )

    def extract_method_block(self,text,method):
        # Handles function method(...), const method = async (...), method: async (...)
        pats=[
            r"(?:async\s+)?"+re.escape(method)+r"\s*\(([^)]*)\)\s*\{",
            r"(?:const|let|var)\s+"+re.escape(method)+r"\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
            re.escape(method)+r"\s*:\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
        ]
        for pat in pats:
            m=re.search(pat,text)
            if not m:
                continue
            start=text.find("{",m.end()-1)
            return self.balanced_block(text,start)
        return ""

    def balanced_block(self,text,start):
        if start<0: return ""
        depth=0; quote=None; esc=False; line=False; block=False
        for i in range(start,min(len(text),start+12000)):
            ch=text[i]; nxt=text[i+1] if i+1<len(text) else ""
            if line:
                if ch=="\n": line=False
                continue
            if block:
                if ch=="*" and nxt=="/": block=False
                continue
            if quote:
                if esc: esc=False
                elif ch=="\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch=="/" and nxt=="/": line=True; continue
            if ch=="/" and nxt=="*": block=True; continue
            if ch in ("'",'"',"`"): quote=ch; continue
            if ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0: return text[start:i+1]
        return text[start:start+12000]

    def extract_body_fields(self,block):
        fields=set()
        aliases={"body","payload","data","input","dto","requestBody","params"}
        # body.title / payload.email
        for a in aliases:
            fields |= set(re.findall(r"\b"+re.escape(a)+r"\.([A-Za-z_$][\w$]*)",block))
            for m in re.finditer(r"(?:const|let|var)\s*\{([^}]+)\}\s*=\s*"+re.escape(a),block):
                for part in m.group(1).split(","):
                    name=part.strip().split(":")[0].strip()
                    if re.match(r"^[A-Za-z_$][\w$]*$",name):
                        fields.add(name)
        # insert/update object shorthand: { title, description, name }
        for m in re.finditer(r"(?:create|insert|update|upsert|save)\s*\(\s*\{([\s\S]{0,1500}?)\}\s*\)",block):
            obj=m.group(1)
            for kv in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*:",obj):
                fields.add(kv.group(1))
        return {f for f in fields if f not in {"id","user","req","res","reply","request","response"}}
