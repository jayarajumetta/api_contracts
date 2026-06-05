from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import yaml

from qaira_semantic_compiler.core.context import RunContext, AgentResult
from qaira_semantic_compiler.core.logging import AgentLogger
from qaira_semantic_compiler.core.safe_runner import SafeAgentRunner

from qaira_semantic_compiler.agents.repo_clone_agent import RepoCloneAgent
from qaira_semantic_compiler.agents.repository_index_agent import RepositoryIndexAgent
from qaira_semantic_compiler.agents.legacy_compiler_agent import LegacySemanticCompilerAgent
from qaira_semantic_compiler.agents.output_analyzer_agent import OutputAnalyzerAgent
from qaira_semantic_compiler.agents.llm_results_analyzer_agent import LLMResultsAnalyzerAgent
from qaira_semantic_compiler.agents.final_test_generation_agent import FinalTestGenerationAgent
from qaira_semantic_compiler.agents.code_generation_agent import CodeGenerationAgent
from qaira_semantic_compiler.agents.git_commit_push_agent import GitCommitPushAgent


def load_config(path: Path | None) -> dict:
    if path and path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


class ModularOrchestratorV60:
    """
    Production-ready modular runtime.

    V60 still preserves the proven legacy semantic compiler as one core agent,
    but wraps it with clean agent contracts, per-agent metrics, fail-open
    execution, repository indexing, LLM result analysis, final generation, and
    git reporting. This is the bridge release that makes the runtime stable
    before moving every inner compiler component into its own separate module.
    """

    def __init__(self, source: Path, output: Path, learning: Path, changed_files: str, cfg: dict):
        self.ctx = RunContext(
            source=source,
            output=output,
            learning=learning,
            changed_files=changed_files,
            config=cfg,
        )
        self.logger = AgentLogger(
            output,
            verbose_console=(cfg.get("logging") or {}).get("verbose_console", True),
        )
        self.runner = SafeAgentRunner(self.ctx, self.logger)

    def run(self) -> int:
        self.logger.console("START", "ModularOrchestratorV60", "initialized")
        self.ctx.output.mkdir(parents=True, exist_ok=True)
        self.ctx.learning.mkdir(parents=True, exist_ok=True)
        self.ctx.write_json("config/effective_config.json", self.ctx.config)

        stages = [
            ("RepoCloneAgent", lambda: RepoCloneAgent(self.ctx, self.logger).run()),
            ("RepositoryIndexAgent", lambda: RepositoryIndexAgent(self.ctx, self.logger).run()),
            ("LegacySemanticCompilerAgent", lambda: LegacySemanticCompilerAgent(self.ctx, self.logger).run()),
            ("OutputAnalyzerAgent", lambda: OutputAnalyzerAgent(self.ctx, self.logger).run()),
            ("LLMResultsAnalyzerAgent", lambda: LLMResultsAnalyzerAgent(self.ctx, self.logger).run()),
            ("FinalTestGenerationAgent", lambda: FinalTestGenerationAgent(self.ctx, self.logger).run()),
            ("CodeGenerationAgent", lambda: CodeGenerationAgent(self.ctx, self.logger).run()),
            ("GitCommitPushAgent", lambda: GitCommitPushAgent(self.ctx, self.logger).run()),
        ]

        fail_open = (self.ctx.config.get("runtime_execution") or {}).get("fail_open_on_agent_error", True)
        for name, fn in stages:
            self.runner.run(name, fn, fail_open=fail_open)

        summary = {
            "version": "v60",
            "status": "completed",
            "agents": [r.__dict__ for r in self.ctx.agent_results],
            "failedAgents": [r.name for r in self.ctx.agent_results if r.status not in {"success", "failed_open"}],
            "failedOpenAgents": [r.name for r in self.ctx.agent_results if r.status == "failed_open"],
        }
        self.ctx.write_json("runtime/modular_orchestrator_report.json", summary)
        self.logger.console("DONE", "ModularOrchestratorV60", "completed", agents=len(self.ctx.agent_results))
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
    return ModularOrchestratorV60(
        source=Path(args.source),
        output=Path(args.output),
        learning=Path(args.learning),
        changed_files=args.changed_files,
        cfg=cfg,
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
