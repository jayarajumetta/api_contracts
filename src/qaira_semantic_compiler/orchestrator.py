from __future__ import annotations
from pathlib import Path
import argparse, yaml, shutil, json

from qaira_semantic_compiler.core.context import RunContext
from qaira_semantic_compiler.core.logger import Logger
from qaira_semantic_compiler.core.runner import AgentRunner
from qaira_semantic_compiler.core.iteration_context import IterationContextStore

from qaira_semantic_compiler.agents.repository_index_agent import RepositoryIndexAgent
from qaira_semantic_compiler.agents.source_detection_agent import SourceDetectionAgent
from qaira_semantic_compiler.agents.route_discovery_agent import RouteDiscoveryAgent
from qaira_semantic_compiler.agents.body_discovery_agent import BodyDiscoveryAgent
from qaira_semantic_compiler.agents.params_discovery_agent import ParamsDiscoveryAgent
from qaira_semantic_compiler.agents.param_type_discovery_agent import ParamTypeDiscoveryAgent
from qaira_semantic_compiler.agents.validation_schema_agent import ValidationSchemaAgent
from qaira_semantic_compiler.agents.import_graph_agent import ImportGraphAgent
from qaira_semantic_compiler.agents.service_graph_agent import ServiceGraphAgent
from qaira_semantic_compiler.agents.service_body_field_agent import ServiceBodyFieldAgent
from qaira_semantic_compiler.agents.db_write_field_agent import DbWriteFieldAgent
from qaira_semantic_compiler.agents.service_body_propagation_agent import ServiceBodyPropagationAgent
from qaira_semantic_compiler.agents.inferred_schema_registry_agent import InferredSchemaRegistryAgent
from qaira_semantic_compiler.agents.schema_attachment_agent import SchemaAttachmentAgent
from qaira_semantic_compiler.agents.required_field_confidence_agent import RequiredFieldConfidenceAgent
from qaira_semantic_compiler.agents.response_discovery_agent import ResponseDiscoveryAgent
from qaira_semantic_compiler.agents.contract_builder_agent import ContractBuilderAgent
from qaira_semantic_compiler.agents.relationship_agent import RelationshipAgent
from qaira_semantic_compiler.agents.test_generation_agent import TestGenerationAgent
from qaira_semantic_compiler.agents.quality_gate_agent import QualityGateAgent
from qaira_semantic_compiler.agents.llm_gateway_agent import LLMGatewayAgent
from qaira_semantic_compiler.agents.artifact_manifest_agent import ArtifactManifestAgent
from qaira_semantic_compiler.agents.results_analyzer_agent import ResultsAnalyzerAgent
from qaira_semantic_compiler.agents.remediation_agent import RemediationAgent
from qaira_semantic_compiler.agents.git_finalization_agent import GitFinalizationAgent
from qaira_semantic_compiler.agents.final_run_report_agent import FinalRunReportAgent
from qaira_semantic_compiler.agents.iteration_llm_reviewer_agent import IterationLLMReviewerAgent
from qaira_semantic_compiler.agents.code_delta_generation_agent import CodeDeltaGenerationAgent

def deep_merge(base, override):
    if not isinstance(base, dict):
        return override
    if not isinstance(override, dict):
        return override if override is not None else base
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def load_config(path):
    # Config override is optional.
    # Default config is bundled inside the image. If /config/config.yaml is absent,
    # mounted as a directory, or invalid, the bundled default still runs.
    package_default = Path(__file__).resolve().parents[2] / "config" / "config.example.yaml"
    cfg = {}
    if package_default.exists() and package_default.is_file():
        try:
            cfg = yaml.safe_load(package_default.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}

    if path:
        p = Path(path)
        if p.exists() and p.is_file():
            try:
                override = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                cfg = deep_merge(cfg, override)
                cfg.setdefault("compatibility", {})["override_config_loaded"] = str(p)
            except Exception as e:
                cfg.setdefault("compatibility", {})["override_config_error"] = str(e)
        else:
            cfg.setdefault("compatibility", {})["override_config_skipped"] = str(p)
    return cfg

class Orchestrator:
    def __init__(self, source, output, learning, config):
        self.ctx=RunContext(Path(source),Path(output),Path(learning),config or {})
        self.ctx.output.mkdir(parents=True,exist_ok=True)
        self.ctx.learning.mkdir(parents=True,exist_ok=True)
        self.logger=Logger(self.ctx.output, console=self.ctx.config.get("logging",{}).get("console",True))
        self.runner=AgentRunner(self.ctx,self.logger)

    def discovery_agents(self):
        return [
            RepositoryIndexAgent,
            SourceDetectionAgent,
            RouteDiscoveryAgent,
            BodyDiscoveryAgent,
            ParamsDiscoveryAgent,
            ParamTypeDiscoveryAgent,
            ValidationSchemaAgent,
            ImportGraphAgent,
            ServiceGraphAgent,
            ServiceBodyFieldAgent,
            DbWriteFieldAgent,
            ServiceBodyPropagationAgent,
            InferredSchemaRegistryAgent,
            SchemaAttachmentAgent,
            RequiredFieldConfidenceAgent,
            ResponseDiscoveryAgent,
            ContractBuilderAgent,
            RelationshipAgent,
            TestGenerationAgent,
            QualityGateAgent,
            LLMGatewayAgent,
            ArtifactManifestAgent,
            ResultsAnalyzerAgent,
        ]

    def reset_iteration_state(self):
        # Keep config; reset in-memory discovered state.
        self.ctx.state.clear()

    def snapshot_iteration(self,iteration):
        dst=self.ctx.output/"iterations"/f"iteration_{iteration}"
        dst.mkdir(parents=True,exist_ok=True)
        for rel in ["summary/scan_summary.json","quality/quality_gate_report.json","analysis/results_analysis.json"]:
            src=self.ctx.output/rel
            if src.exists():
                out=dst/rel
                out.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(src,out)

    def run(self):
        self.logger.log("START","Orchestrator","auto-iterative runtime started")
        self.ctx.write_json("config/effective_config.json", self.ctx.config)
        self.ctx.write_json("runtime/config_compatibility_report.json", {"acceptedLegacySections": ["agentic_runtime","git_push","llm","llm_invocation"], "autoIterationSource": "auto_iteration_or_agentic_runtime", "gitSource": "git_finalization_or_git_push", "llmSource": "llm_review_or_llm"})

        auto=self.ctx.config.get("auto_iteration",{}) or self.ctx.config.get("agentic_runtime",{})
        max_iter=int(auto.get("max_iterations", auto.get("max_iterations_per_run", 1 if not auto.get("enabled",False) else 5)))
        threshold=float(auto.get("min_score_percent", auto.get("quality_threshold_percent", 90)))
        stop_when_passes=bool(auto.get("stop_when_quality_passes", auto.get("stop_when_quality_gate_passes", True)))
        apply_remediation=bool(auto.get("apply_known_remediations",True))

        best={"iteration":0,"score":-1}

        for iteration in range(1,max_iter+1):
            self.logger.log("ITERATION","Orchestrator",f"iteration {iteration} started")
            self.reset_iteration_state()
            self.ctx.state["iteration"]=iteration

            for cls in self.discovery_agents():
                self.runner.run(cls(self.ctx,self.logger))

            quality=self.ctx.read_json("quality/quality_gate_report.json",{}) or {}
            summary=self.ctx.read_json("summary/scan_summary.json",{}) or {}
            analysis=self.ctx.read_json("analysis/results_analysis.json",{}) or {}
            score=float(quality.get("score",0) or 0)

            IterationContextStore(self.ctx).load().add_iteration(iteration,self.ctx.results,summary,quality,analysis)

            if score>best["score"]:
                best={"iteration":iteration,"score":score,"summary":summary}
                self.ctx.state["bestIteration"]=best

            self.snapshot_iteration(iteration)

            # Exactly one compact LLM review per iteration/run, not many agent log prompts.
            self.runner.run(IterationLLMReviewerAgent(self.ctx,self.logger))
            self.runner.run(CodeDeltaGenerationAgent(self.ctx,self.logger))

            passed=bool(quality.get("passed",False))
            self.logger.log("ITERATION","Orchestrator",f"iteration {iteration} completed",score=score,passed=passed)

            if stop_when_passes and passed and score>=threshold:
                break

            if apply_remediation and iteration<max_iter:
                self.runner.run(RemediationAgent(self.ctx,self.logger))

        self.ctx.write_json("runtime/best_iteration.json",best)

        # Final one-time stages
        self.runner.run(GitFinalizationAgent(self.ctx,self.logger))
        self.runner.run(FinalRunReportAgent(self.ctx,self.logger))

        self.ctx.write_json("runtime/orchestrator_report.json",{"status":"completed","bestIteration":best,"agents":[r.__dict__ for r in self.ctx.results]})
        self.logger.log("DONE","Orchestrator","completed",bestIteration=best)
        return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",default="/repo")
    ap.add_argument("--output",default="/output")
    ap.add_argument("--learning",default="/learning")
    ap.add_argument("--config",default="/config/config.yaml")
    a=ap.parse_args()
    return Orchestrator(a.source,a.output,a.learning,load_config(a.config)).run()

if __name__=="__main__":
    raise SystemExit(main())
