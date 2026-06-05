from qaira_semantic_compiler.core.context import AgentResult

class RemediationAgent:
    name="RemediationAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        analysis=self.ctx.state.get("analysis") or self.ctx.read_json("analysis/results_analysis.json",{}) or {}
        actions=analysis.get("nextRemediations") or []
        applied=[]
        cfg=self.ctx.config

        # These remediations are deterministic config relaxations. They do not patch source code.
        for action in actions:
            if action=="enable_balanced_route_fallback_scan_all_js_ts":
                cfg.setdefault("agents",{})["route_discovery"]=True
                applied.append(action)
            elif action=="relax_body_presence_detection_and_service_arg_detection":
                cfg.setdefault("pattern_establishment",{})["relaxed_body_detection"]=True
                applied.append(action)
            elif action=="enable_service_and_db_field_pattern_propagation":
                cfg.setdefault("pattern_establishment",{})["service_body_field_extraction"]=True
                cfg.setdefault("pattern_establishment",{})["db_write_field_extraction"]=True
                cfg.setdefault("pattern_establishment",{})["service_body_propagation"]=True
                applied.append(action)
            elif action=="enable_import_resolution_and_call_argument_capture":
                cfg.setdefault("agents",{})["service_graph"]=True
                applied.append(action)
            elif action=="enable_inferred_schema_registry":
                cfg.setdefault("pattern_establishment",{})["inferred_schema_registry"]=True
                applied.append(action)
            elif action=="rerun_test_generation_after_contract_builder":
                cfg.setdefault("agents",{})["test_generation"]=True
                applied.append(action)

        self.ctx.write_json("analysis/remediation_report.json",{"requested":actions,"applied":applied})
        return AgentResult(self.name,"success",0.85,{"requested":len(actions),"applied":len(applied)},{"applied":applied})
