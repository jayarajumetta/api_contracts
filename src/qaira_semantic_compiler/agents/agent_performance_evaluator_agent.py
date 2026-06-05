from qaira_semantic_compiler.core.context import AgentResult

class AgentPerformanceEvaluatorAgent:
    name = "AgentPerformanceEvaluatorAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        summary = self.ctx.read_json("summary/scan_summary.json", {}) or {}
        quality = self.ctx.read_json("quality/quality_gate_report.json", {}) or {}
        agent_scores = []

        metric_rules = {
            "RouteDiscoveryAgent": {
                "score": 100 if summary.get("apiContracts", 0) > 0 else 0,
                "evidence": {"apiContracts": summary.get("apiContracts", 0)},
                "threshold": 95,
                "repoSpecificHints": ["scan route/controller files", "fallback all JS/TS route calls", "balanced call parser"]
            },
            "BodyDiscoveryAgent": {
                "score": min(100, float(summary.get("bodyDetectionRate", 0) or 0)),
                "evidence": {
                    "bodyExpected": summary.get("bodyExpected"),
                    "bodyDetected": summary.get("bodyDetected"),
                    "bodyDetectionRate": summary.get("bodyDetectionRate")
                },
                "threshold": 90,
                "repoSpecificHints": ["req.body", "request.body", "payload aliases", "service call body arguments"]
            },
            "ServiceGraphAgent": {
                "score": 100 if summary.get("serviceEdges", 0) > 0 else 20,
                "evidence": {"serviceEdges": summary.get("serviceEdges", 0)},
                "threshold": 90,
                "repoSpecificHints": ["import resolution", "service.method(args)", "call argument capture"]
            },
            "ServiceBodyFieldAgent": {
                "score": min(100, float(summary.get("bodyFieldKnownRate", 0) or 0)),
                "evidence": {
                    "bodyFieldsKnown": summary.get("bodyFieldsKnown"),
                    "bodyFieldKnownRate": summary.get("bodyFieldKnownRate"),
                    "serviceBodyPatterns": summary.get("serviceBodyPatterns")
                },
                "threshold": 80,
                "repoSpecificHints": ["map route arg position to service param", "body alias fields", "destructured body fields"]
            },
            "DbWriteFieldAgent": {
                "score": 100 if summary.get("dbWritePatterns", 0) > 0 else 30,
                "evidence": {"dbWritePatterns": summary.get("dbWritePatterns")},
                "threshold": 60,
                "repoSpecificHints": ["SQL insert/update", "Prisma data", "Knex insert/update", "repository create/save"]
            },
            "InferredSchemaRegistryAgent": {
                "score": 100 if summary.get("inferredSchemaAttachments", 0) > 0 else 20,
                "evidence": {
                    "inferredSchemas": summary.get("inferredSchemas"),
                    "inferredSchemaAttachments": summary.get("inferredSchemaAttachments")
                },
                "threshold": 90,
                "repoSpecificHints": ["generate schema from propagated body fields"]
            },
            "TestGenerationAgent": {
                "score": 100 if summary.get("testsGenerated") and summary.get("negativeTestsGenerated") and summary.get("edgeTestsGenerated") else 70,
                "evidence": {
                    "testsGenerated": summary.get("testsGenerated"),
                    "negativeTestsGenerated": summary.get("negativeTestsGenerated"),
                    "edgeTestsGenerated": summary.get("edgeTestsGenerated")
                },
                "threshold": 90,
                "repoSpecificHints": ["status assertions", "body assertions", "extractors", "data references"]
            }
        }

        for agent, rule in metric_rules.items():
            score = round(float(rule["score"]), 2)
            threshold = float(rule["threshold"])
            agent_scores.append({
                "agent": agent,
                "score": score,
                "threshold": threshold,
                "passed": score >= threshold,
                "evidence": rule["evidence"],
                "repoSpecificHints": rule["repoSpecificHints"],
                "suggestedInputForNextRun": self.suggest_input(agent, score, threshold, rule["evidence"])
            })

        failed = [a for a in agent_scores if not a["passed"]]
        report = {
            "overallScore": quality.get("score", 0),
            "overallPassed": quality.get("passed", False),
            "agentScores": agent_scores,
            "weakAgents": failed,
            "llmInputPurpose": "Feed this compact report to LLM once, asking for repo-specific agent delta suggestions only."
        }
        self.ctx.write_json("self_healing/agent_performance_report.json", report)
        self.ctx.state["agentPerformanceReport"] = report
        return AgentResult(self.name, "success", 0.95, {"weakAgents": len(failed)}, report)

    def suggest_input(self, agent, score, threshold, evidence):
        if score >= threshold:
            return {"action": "keep_current_logic", "reason": "agent passed threshold"}
        if agent == "BodyDiscoveryAgent":
            return {"action": "expand_body_alias_patterns", "inputs": ["route handlers", "service call args", "req.body aliases"], "evidence": evidence}
        if agent == "ServiceBodyFieldAgent":
            return {"action": "improve_service_param_mapping", "inputs": ["serviceEdges.args", "service method params", "body alias usage"], "evidence": evidence}
        if agent == "DbWriteFieldAgent":
            return {"action": "expand_db_write_extractors", "inputs": ["called service method body only", "SQL/ORM writes"], "evidence": evidence}
        return {"action": "llm_review_agent_specific_delta", "evidence": evidence}
