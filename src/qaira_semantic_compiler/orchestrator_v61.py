from __future__ import annotations

import argparse
from pathlib import Path
import yaml

from qaira_semantic_compiler.core.context import RunContext
from qaira_semantic_compiler.core.logging import AgentLogger
from qaira_semantic_compiler.core.safe_runner import SafeAgentRunner

from qaira_semantic_compiler.agents.planner_agent import PlannerAgent
from qaira_semantic_compiler.agents.state_machine_agent import StateMachineAgent
from qaira_semantic_compiler.agents.repo_clone_agent import RepoCloneAgent
from qaira_semantic_compiler.agents.repository_index_agent import RepositoryIndexAgent
from qaira_semantic_compiler.agents.legacy_compiler_agent import LegacySemanticCompilerAgent
from qaira_semantic_compiler.agents.output_analyzer_agent import OutputAnalyzerAgent
from qaira_semantic_compiler.agents.verifier_agent import VerifierAgent
from qaira_semantic_compiler.agents.quality_gate_agent import QualityGateAgent
from qaira_semantic_compiler.agents.llm_results_analyzer_agent import LLMResultsAnalyzerAgent
from qaira_semantic_compiler.agents.final_test_generation_agent import FinalTestGenerationAgent
from qaira_semantic_compiler.agents.artifact_manifest_agent import ArtifactManifestAgent
from qaira_semantic_compiler.agents.code_generation_agent import CodeGenerationAgent
from qaira_semantic_compiler.agents.git_commit_push_agent import GitCommitPushAgent


def load_config(path: Path | None) -> dict:
    if path and path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


class FinalAgenticOrchestratorV61:
    def __init__(self, source: Path, output: Path, learning: Path, changed_files: str, cfg: dict):
        self.ctx = RunContext(source=source, output=output, learning=learning, changed_files=changed_files, config=cfg)
        self.logger = AgentLogger(output, verbose_console=(cfg.get("logging") or {}).get("verbose_console", True))
        self.runner = SafeAgentRunner(self.ctx, self.logger)

    def run(self) -> int:
        self.logger.console("START", "FinalAgenticOrchestratorV61", "initialized")
        self.ctx.output.mkdir(parents=True, exist_ok=True)
        self.ctx.learning.mkdir(parents=True, exist_ok=True)
        self.ctx.write_json("config/effective_config.json", self.ctx.config)

        fail_open = (self.ctx.config.get("runtime_execution") or {}).get("fail_open_on_agent_error", True)

        stages = [
            ("PlannerAgent", lambda: PlannerAgent(self.ctx, self.logger).run()),
            ("StateMachine_INIT", lambda: StateMachineAgent(self.ctx, self.logger).run("INIT", "start")),
            ("RepoCloneAgent", lambda: RepoCloneAgent(self.ctx, self.logger).run()),
            ("RepositoryIndexAgent", lambda: RepositoryIndexAgent(self.ctx, self.logger).run()),
            ("StateMachine_DISCOVERY", lambda: StateMachineAgent(self.ctx, self.logger).run("DISCOVERY", "start")),
            ("LegacySemanticCompilerAgent", lambda: LegacySemanticCompilerAgent(self.ctx, self.logger).run()),
            ("OutputAnalyzerAgent", lambda: OutputAnalyzerAgent(self.ctx, self.logger).run()),
            ("VerifierAgent", lambda: VerifierAgent(self.ctx, self.logger).run()),
            ("QualityGateAgent", lambda: QualityGateAgent(self.ctx, self.logger).run()),
            ("LLMResultsAnalyzerAgent", lambda: LLMResultsAnalyzerAgent(self.ctx, self.logger).run()),
            ("FinalTestGenerationAgent", lambda: FinalTestGenerationAgent(self.ctx, self.logger).run()),
            ("ArtifactManifestAgent", lambda: ArtifactManifestAgent(self.ctx, self.logger).run()),
            ("CodeGenerationAgent", lambda: CodeGenerationAgent(self.ctx, self.logger).run()),
            ("GitCommitPushAgent", lambda: GitCommitPushAgent(self.ctx, self.logger).run()),
            ("StateMachine_COMPLETE", lambda: StateMachineAgent(self.ctx, self.logger).run("COMPLETE", "done")),
        ]

        for name, fn in stages:
            self.runner.run(name, fn, fail_open=fail_open)

        report = {
            "version": "v61",
            "status": "completed",
            "agents": [r.__dict__ for r in self.ctx.agent_results],
            "failedOpenAgents": [r.name for r in self.ctx.agent_results if r.status == "failed_open"],
            "failedAgents": [r.name for r in self.ctx.agent_results if r.status == "failed"],
        }
        self.ctx.write_json("runtime/final_agentic_orchestrator_report.json", report)
        self.logger.console("DONE", "FinalAgenticOrchestratorV61", "completed", agents=len(self.ctx.agent_results))
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="/repo")
    ap.add_argument("--output", default="/output")
    ap.add_argument("--learning", default="/learning")
    ap.add_argument("--config", default="/config/config.yaml")
    ap.add_argument("--changed-files", default="")
    args = ap.parse_args()
    cfg = load_config(Path(args.config) if args.config else None)
    return FinalAgenticOrchestratorV61(Path(args.source), Path(args.output), Path(args.learning), args.changed_files, cfg).run()


if __name__ == "__main__":
    raise SystemExit(main())
