from qaira_semantic_compiler.core.context import AgentResult
from qaira_semantic_compiler.core.patch_library import PatchLibrary, set_deep, snapshot_config, now

class PatchLibraryAgent:
    name = "PatchLibraryAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        cfg = self.ctx.config.get("patch_library", {}) or {}
        enabled = bool(cfg.get("enabled", True))
        if not enabled:
            report = {"enabled": False, "applied": [], "reason": "patch_library_disabled"}
            self.ctx.write_json("self_healing/patch_library_report.json", report)
            return AgentResult(self.name, "success", 0.9, {"applied": 0}, report)

        lib = PatchLibrary()
        self.ctx.write_json("self_healing/patch_library_registry.json", {"actions": lib.list_actions()})

        perf = self.ctx.state.get("agentPerformanceReport") or self.ctx.read_json("self_healing/agent_performance_report.json", {}) or {}
        advice = self.ctx.state.get("selfHealingLLMAdvice") or self.ctx.read_json("self_healing/llm_advice.json", {}) or {}
        weak = perf.get("weakAgents", [])
        llm_deltas = advice.get("suggestedAgentDeltas", []) or []

        selected = lib.choose_actions(
            weak,
            llm_deltas,
            max_count=int(cfg.get("max_patches_per_iteration", 5)),
            min_confidence=float(cfg.get("min_confidence", 0.6))
        )

        before = snapshot_config(self.ctx.config)
        applied = []
        blocked = []

        for item in selected:
            action = item["action"]
            if not self.is_approved(action):
                blocked.append({"action": action, "reason": "not_approved_by_config"})
                continue
            set_deep(self.ctx.config, action["config_path"], action["value"])
            applied.append({
                "actionId": action["action_id"],
                "agent": action["agent"],
                "description": action["description"],
                "expectedMetric": action["expected_metric"],
                "risk": action["risk"],
                "source": item.get("source"),
                "confidence": item.get("confidence"),
                "appliedAt": now()
            })

        report = {
            "enabled": True,
            "selected": selected,
            "applied": applied,
            "blocked": blocked,
            "beforeConfigSnapshotSaved": True,
            "afterPatchRuntime": self.ctx.config.get("patch_runtime", {}),
            "note": "Patches mutate runtime config/pattern behavior for next iteration. Arbitrary LLM code is not executed."
        }
        self.ctx.state["patchLibraryReport"] = report
        self.ctx.state["prePatchConfigSnapshot"] = before
        self.ctx.write_json("self_healing/patch_library_report.json", report)
        self.ctx.write_json("self_healing/pre_patch_config_snapshot.json", before)
        self.ctx.write_json("self_healing/post_patch_effective_config.json", self.ctx.config)
        return AgentResult(self.name, "success", 0.9, {"applied": len(applied), "blocked": len(blocked)}, report)

    def is_approved(self, action):
        approved = (self.ctx.config.get("patch_library", {}) or {}).get("approved_actions", {})
        allowed = approved.get(action["agent"], [])
        return action["action_id"] in allowed
