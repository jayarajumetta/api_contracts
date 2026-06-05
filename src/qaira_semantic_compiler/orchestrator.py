from __future__ import annotations
from pathlib import Path
import argparse, yaml

from qaira_semantic_compiler.core.context import RunContext
from qaira_semantic_compiler.core.logger import Logger
from qaira_semantic_compiler.core.runner import AgentRunner

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
from qaira_semantic_compiler.agents.response_discovery_agent import ResponseDiscoveryAgent
from qaira_semantic_compiler.agents.contract_builder_agent import ContractBuilderAgent
from qaira_semantic_compiler.agents.relationship_agent import RelationshipAgent
from qaira_semantic_compiler.agents.test_generation_agent import TestGenerationAgent
from qaira_semantic_compiler.agents.quality_gate_agent import QualityGateAgent
from qaira_semantic_compiler.agents.llm_gateway_agent import LLMGatewayAgent
from qaira_semantic_compiler.agents.artifact_manifest_agent import ArtifactManifestAgent

def load_config(path):
    p=Path(path)
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}

class Orchestrator:
    def __init__(self, source, output, learning, config):
        self.ctx=RunContext(Path(source),Path(output),Path(learning),config or {})
        self.ctx.output.mkdir(parents=True,exist_ok=True)
        self.ctx.learning.mkdir(parents=True,exist_ok=True)
        self.logger=Logger(self.ctx.output, console=self.ctx.config.get("logging",{}).get("console",True))
        self.runner=AgentRunner(self.ctx,self.logger)

    def run(self):
        self.logger.log("START","Orchestrator","pattern-establishment runtime started")
        self.ctx.write_json("config/effective_config.json", self.ctx.config)

        agents=[
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
            ResponseDiscoveryAgent,
            ContractBuilderAgent,
            RelationshipAgent,
            TestGenerationAgent,
            QualityGateAgent,
            LLMGatewayAgent,
            ArtifactManifestAgent,
        ]

        for cls in agents:
            self.runner.run(cls(self.ctx,self.logger))

        self.ctx.write_json("runtime/orchestrator_report.json",{"status":"completed","agents":[r.__dict__ for r in self.ctx.results]})
        self.logger.log("DONE","Orchestrator","completed",agents=len(self.ctx.results))
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
