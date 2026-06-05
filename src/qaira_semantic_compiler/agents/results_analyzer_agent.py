from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.llm_client import LLMClient

class ResultsAnalyzerAgent:
    name="ResultsAnalyzerAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        summary=self.ctx.read_json("summary/scan_summary.json",{}) or {}
        quality=self.ctx.read_json("quality/quality_gate_report.json",{}) or {}
        issues=self.rank_issues(summary,quality)
        score=float(quality.get("score",0) or 0)
        threshold=float((self.ctx.config.get("auto_iteration") or {}).get("min_score_percent",90))
        accepted=score>=threshold and not self.has_critical_issue(summary)
        result={
            "score":score,
            "threshold":threshold,
            "accepted":accepted,
            "issues":issues,
            "nextRemediations":self.remediations(issues),
            "summary":summary,
            "reactSafety":{"strictJsonTransport":True,"malformedQuoteEscapeFailOpen":True}
        }
        llm=LLMClient(self.ctx,self.logger).review("ResultsAnalyzerAgent",result,default={"accepted":accepted,"suggestions":result["nextRemediations"]})
        result["llmReview"]=llm
        self.ctx.state["analysis"]=result
        self.ctx.write_json("analysis/results_analysis.json",result)
        return AgentResult(self.name,"success",min(1,score/100),{"score":score,"issues":len(issues),"accepted":accepted},result)

    def has_critical_issue(self,s):
        return s.get("apiContracts",0)==0 or not s.get("testsGenerated",False)

    def rank_issues(self,s,q):
        issues=[]
        if s.get("apiContracts",0)==0:
            issues.append({"rank":1,"key":"route_discovery","severity":"critical","message":"No API contracts discovered."})
        if s.get("bodyDetectionRate",0)<90:
            issues.append({"rank":2,"key":"body_detection","severity":"high","message":"Body detection below 90%."})
        if s.get("bodyFieldKnownRate",0)<80:
            issues.append({"rank":3,"key":"body_fields_known","severity":"medium","message":"Body field inference below 80%."})
        if s.get("serviceEdges",0)==0:
            issues.append({"rank":4,"key":"service_graph","severity":"high","message":"Service graph not connected."})
        if s.get("inferredSchemaAttachments",0)==0:
            issues.append({"rank":5,"key":"schema_attachment","severity":"medium","message":"No inferred schema attachments."})
        if not s.get("testsGenerated",False):
            issues.append({"rank":6,"key":"test_generation","severity":"critical","message":"Tests not generated."})
        return issues

    def remediations(self,issues):
        mapping={
            "route_discovery":"enable_balanced_route_fallback_scan_all_js_ts",
            "body_detection":"relax_body_presence_detection_and_service_arg_detection",
            "body_fields_known":"enable_service_and_db_field_pattern_propagation",
            "service_graph":"enable_import_resolution_and_call_argument_capture",
            "schema_attachment":"enable_inferred_schema_registry",
            "test_generation":"rerun_test_generation_after_contract_builder"
        }
        return [mapping[i["key"]] for i in issues if i["key"] in mapping]
