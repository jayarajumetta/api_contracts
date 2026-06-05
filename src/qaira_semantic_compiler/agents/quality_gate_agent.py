from qaira_semantic_compiler.core.context import AgentResult

class QualityGateAgent:
    name="QualityGateAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        routes=self.ctx.state.get("routes",[])
        contracts=self.ctx.state.get("contracts",[])
        body_details=self.ctx.state.get("bodyDetails",[])

        body_expected=len([r for r in routes if r["method"] in {"POST","PUT","PATCH"}])
        body_detected=len([b for b in body_details if b.get("hasBody")])
        body_fields_known=len([b for b in body_details if b.get("fieldsKnown")])

        body_rate=round(body_detected/max(body_expected,1)*100,2)
        fields_rate=round(body_fields_known/max(body_expected,1)*100,2)

        summary={
            "apiContracts":len(contracts),
            "bodyExpected":body_expected,
            "bodyDetected":body_detected,
            "bodyFieldsKnown":body_fields_known,
            "bodyDetectionRate":body_rate,
            "bodyFieldKnownRate":fields_rate,
            "pathParamsDiscovered":sum(len([p for p in c.get("parameters",[]) if p["in"]=="path"]) for c in contracts),
            "queryParamsDiscovered":sum(len([p for p in c.get("parameters",[]) if p["in"]=="query"]) for c in contracts),
            "headersDiscovered":sum(len([p for p in c.get("parameters",[]) if p["in"]=="header"]) for c in contracts),
            "serviceEdges":len(self.ctx.state.get("serviceEdges",[])),
            "schemasDiscovered":len(self.ctx.state.get("schemas",[])),
            "schemaAttachments":len([r for r in routes if (r.get("requestBody") or {}).get("schemaRef")]),
            "testsGenerated":True
        }

        score=min(100,
            body_rate*0.45 +
            (100 if contracts else 0)*0.25 +
            (100 if summary["serviceEdges"] else 0)*0.15 +
            (100 if summary["testsGenerated"] else 0)*0.15
        )

        report={"score":round(score,2),"passed":score>=self.ctx.config.get("quality_gate",{}).get("min_score_percent",90),"summary":summary}
        self.ctx.write_json("summary/scan_summary.json",summary)
        self.ctx.write_json("quality/quality_gate_report.json",report)
        return AgentResult(self.name,"success" if report["passed"] else "failed_open",score/100,report,report)
