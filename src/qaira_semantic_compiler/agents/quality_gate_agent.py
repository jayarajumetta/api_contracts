from qaira_semantic_compiler.core.context import AgentResult

BODY_METHODS={"POST","PUT","PATCH"}

class QualityGateAgent:
    name="QualityGateAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        routes=self.ctx.state.get("routes",[])
        contracts=self.ctx.state.get("contracts",[])
        body_details=self.ctx.state.get("bodyDetails",[])
        body_detail_by_id={b["routeId"]:b for b in body_details}

        expected_routes=[r for r in routes if r["method"] in BODY_METHODS]
        body_expected=len(expected_routes)
        body_detected=len([r for r in expected_routes if body_detail_by_id.get(r["id"],{}).get("hasBody") or r.get("requestBody")])
        body_fields_known=len([
            r for r in expected_routes
            if ((r.get("requestBody") or {}).get("properties") or {})
        ])

        body_rate=min(100,round(body_detected/max(body_expected,1)*100,2))
        fields_rate=min(100,round(body_fields_known/max(body_expected,1)*100,2))

        schema_attachments=len([
            r for r in expected_routes
            if (r.get("requestBody") or {}).get("schemaRef")
        ])

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
            "inferredSchemas":len(self.ctx.state.get("inferredSchemas",[])),
            "schemaAttachments":schema_attachments,
            "serviceBodyPatterns":len(self.ctx.state.get("serviceBodyFieldsByRoute",{})),
            "dbWritePatterns":len(self.ctx.state.get("dbWriteFieldsByRoute",{})),
            "testsGenerated":True
        }

        score=min(100,
            body_rate*0.35 +
            fields_rate*0.25 +
            (100 if contracts else 0)*0.15 +
            (100 if summary["serviceEdges"] else 0)*0.10 +
            (100 if summary["inferredSchemas"] else 0)*0.10 +
            (100 if summary["testsGenerated"] else 0)*0.05
        )

        report={"score":round(score,2),"passed":score>=self.ctx.config.get("quality_gate",{}).get("min_score_percent",90),"summary":summary}
        self.ctx.write_json("summary/scan_summary.json",summary)
        self.ctx.write_json("quality/quality_gate_report.json",report)
        return AgentResult(self.name,"success" if report["passed"] else "failed_open",score/100,report,report)
