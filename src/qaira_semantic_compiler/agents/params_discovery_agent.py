from qaira_semantic_compiler.core.context import AgentResult
import re
class ParamsDiscoveryAgent:
    name="ParamsDiscoveryAgent"
    def __init__(self, ctx, logger): self.ctx=ctx; self.logger=logger
    def run(self):
        routes=self.ctx.state.get("routes",[]); path_count=query_count=header_count=0
        for r in routes:
            params=[]
            for p in re.findall(r":([A-Za-z_][\w]*)|\{([A-Za-z_][\w]*)\}", r["path"]):
                name=p[0] or p[1]; params.append({"name":name,"in":"path","type":"string"}); path_count+=1
            h=r.get("handler","")
            for q in sorted(set(re.findall(r"(?:req|request)\.query\.([A-Za-z_$][\w$]*)",h))):
                params.append({"name":q,"in":"query","type":"string"}); query_count+=1
            for hd in sorted(set(re.findall(r"(?:req|request)\.headers\[?['\"]?([A-Za-z0-9_-]+)",h))):
                params.append({"name":hd,"in":"header","type":"string"}); header_count+=1
            r["parameters"]=params
        result={"pathParams":path_count,"queryParams":query_count,"headers":header_count}
        self.ctx.write_json("discovery/params_discovery.json", result)
        return AgentResult(self.name,"success",0.9,result,result)
