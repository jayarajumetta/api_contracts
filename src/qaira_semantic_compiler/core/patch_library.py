from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Any
import copy, datetime

@dataclass
class PatchAction:
    action_id: str
    agent: str
    description: str
    risk: str
    config_path: List[str]
    value: Any
    expected_metric: str

class PatchLibrary:
    def __init__(self):
        self.actions: Dict[str, PatchAction] = {}
        self._register_defaults()

    def _add(self, action_id, agent, description, risk, config_path, value, expected_metric):
        self.actions[action_id] = PatchAction(action_id, agent, description, risk, config_path, value, expected_metric)

    def _register_defaults(self):
        self._add("ROUTE_ENABLE_GLOBAL_JS_TS_SCAN", "RouteDiscoveryAgent", "Scan all JS/TS files when route/controller hints miss routes.", "low", ["patch_runtime","route_discovery","global_scan"], True, "apiContracts")
        self._add("ROUTE_ENABLE_BALANCED_CALL_SCANNER", "RouteDiscoveryAgent", "Use balanced parenthesis route-call scanner.", "low", ["patch_runtime","route_discovery","balanced_scanner"], True, "apiContracts")
        self._add("ROUTE_ENABLE_PREFIX_MOUNT_DISCOVERY", "RouteDiscoveryAgent", "Enable router prefix/mount discovery for nested routes.", "medium", ["patch_runtime","route_discovery","prefix_mounts"], True, "apiContracts")

        self._add("BODY_ADD_COMMON_ALIASES", "BodyDiscoveryAgent", "Add common body aliases from pattern registry.", "low", ["patch_runtime","body_discovery","common_aliases"], True, "bodyDetected")
        self._add("BODY_ENABLE_SERVICE_ARG_BODY_DETECTION", "BodyDiscoveryAgent", "Treat service call arguments containing req.body/body aliases as body evidence.", "low", ["patch_runtime","body_discovery","service_arg_body"], True, "bodyDetected")
        self._add("BODY_ENABLE_DESTRUCTURING_DETECTION", "BodyDiscoveryAgent", "Detect const {x} = req.body / alias patterns.", "low", ["patch_runtime","body_discovery","destructuring"], True, "bodyFieldsKnown")
        self._add("BODY_ENABLE_NESTED_FIELD_DETECTION", "BodyDiscoveryAgent", "Detect nested body fields safely.", "medium", ["patch_runtime","body_discovery","nested_fields"], True, "bodyFieldsKnown")

        self._add("PARAM_ENABLE_QUERY_DESTRUCTURING", "ParamsDiscoveryAgent", "Detect const {x}=req.query.", "low", ["patch_runtime","params","query_destructuring"], True, "queryParamsDiscovered")
        self._add("PARAM_ENABLE_HEADER_DETECTION", "ParamsDiscoveryAgent", "Detect req.headers and header getter patterns.", "low", ["patch_runtime","params","headers"], True, "headersDiscovered")

        self._add("SERVICE_ENABLE_CALL_ARGUMENT_CAPTURE", "ServiceGraphAgent", "Capture service.method(args) arguments.", "low", ["patch_runtime","service_graph","call_args"], True, "serviceEdges")
        self._add("SERVICE_ENABLE_IMPORT_FALLBACK_BY_STEM", "ServiceGraphAgent", "Resolve service imports by filename stem fallback.", "medium", ["patch_runtime","service_graph","stem_fallback"], True, "serviceEdges")
        self._add("SERVICE_ENABLE_DEFAULT_EXPORT_RESOLUTION", "ServiceGraphAgent", "Resolve default export service objects.", "medium", ["patch_runtime","service_graph","default_export"], True, "serviceEdges")

        self._add("SERVICE_BODY_ENABLE_PARAM_POSITION_MAPPING", "ServiceBodyFieldAgent", "Map route call argument position to service method parameter position.", "low", ["patch_runtime","service_body","param_position_mapping"], True, "bodyFieldsKnown")
        self._add("SERVICE_BODY_ENABLE_OBJECT_LITERAL_EXTRACTION", "ServiceBodyFieldAgent", "Extract fields from object literals passed to services.", "low", ["patch_runtime","service_body","object_literals"], True, "bodyFieldsKnown")
        self._add("SERVICE_BODY_ENABLE_NESTED_OBJECT_KEYS", "ServiceBodyFieldAgent", "Extract nested object keys with filtering.", "medium", ["patch_runtime","service_body","nested_object_keys"], True, "bodyFieldsKnown")

        self._add("DB_ENABLE_SQL_INSERT_UPDATE", "DbWriteFieldAgent", "Extract SQL insert/update columns.", "low", ["patch_runtime","db_write","sql_insert_update"], True, "dbWritePatterns")
        self._add("DB_ENABLE_PRISMA_DATA_OBJECT", "DbWriteFieldAgent", "Extract Prisma data object fields.", "low", ["patch_runtime","db_write","prisma_data"], True, "dbWritePatterns")
        self._add("DB_ENABLE_KNEX_REPOSITORY_WRITES", "DbWriteFieldAgent", "Extract Knex/repository create/update/save object fields.", "low", ["patch_runtime","db_write","knex_repository"], True, "dbWritePatterns")
        self._add("DB_SCOPE_TO_CALLED_METHOD", "DbWriteFieldAgent", "Scope DB extraction to called service method only.", "low", ["patch_runtime","db_write","scope_called_method"], True, "bodyFieldKnownRate")

        self._add("SCHEMA_ENABLE_INFERRED_REQUEST_SCHEMA", "InferredSchemaRegistryAgent", "Generate request schemas from propagated body fields.", "low", ["patch_runtime","schema","inferred_request_schema"], True, "inferredSchemas")
        self._add("SCHEMA_ENABLE_REQUIRED_FIELD_HEURISTICS", "InferredSchemaRegistryAgent", "Add required field heuristics.", "low", ["patch_runtime","schema","required_heuristics"], True, "inferredSchemaAttachments")

        self._add("TEST_ENABLE_STATUS_ASSERTIONS", "TestGenerationAgent", "Add status code assertions to Postman tests.", "low", ["patch_runtime","test_generation","status_assertions"], True, "testsGenerated")
        self._add("TEST_ENABLE_RESPONSE_ASSERTIONS", "TestGenerationAgent", "Add response body assertions.", "low", ["patch_runtime","test_generation","response_assertions"], True, "testsGenerated")
        self._add("TEST_ENABLE_EXTRACTORS", "TestGenerationAgent", "Add id/token extractors.", "low", ["patch_runtime","test_generation","extractors"], True, "testsGenerated")
        self._add("TEST_ENABLE_DATA_REFERENCES", "TestGenerationAgent", "Add data reference files and variables.", "low", ["patch_runtime","test_generation","data_references"], True, "testsGenerated")
        self._add("TEST_ENABLE_NEGATIVE_EDGE_TESTS", "TestGenerationAgent", "Add negative and edge tests.", "low", ["patch_runtime","test_generation","negative_edge"], True, "negativeTestsGenerated")

    def list_actions(self):
        return [asdict(a) for a in self.actions.values()]

    def allowed_for_agent(self, agent: str):
        return [asdict(a) for a in self.actions.values() if a.agent == agent]

    def action(self, action_id: str):
        return self.actions.get(action_id)

    def choose_actions(self, weak_agents: List[Dict[str, Any]], llm_deltas: List[Dict[str, Any]], max_count: int = 5, min_confidence: float = 0.6):
        selected = []
        seen = set()

        # First map deterministic weak-agent symptoms.
        for item in weak_agents or []:
            agent = item.get("agent")
            evidence = item.get("evidence", {})
            if agent == "BodyDiscoveryAgent":
                candidates = ["BODY_ADD_COMMON_ALIASES", "BODY_ENABLE_SERVICE_ARG_BODY_DETECTION", "BODY_ENABLE_DESTRUCTURING_DETECTION"]
            elif agent == "ServiceBodyFieldAgent":
                candidates = ["SERVICE_BODY_ENABLE_PARAM_POSITION_MAPPING", "SERVICE_BODY_ENABLE_OBJECT_LITERAL_EXTRACTION"]
            elif agent == "DbWriteFieldAgent":
                candidates = ["DB_SCOPE_TO_CALLED_METHOD", "DB_ENABLE_SQL_INSERT_UPDATE", "DB_ENABLE_PRISMA_DATA_OBJECT", "DB_ENABLE_KNEX_REPOSITORY_WRITES"]
            elif agent == "RouteDiscoveryAgent":
                candidates = ["ROUTE_ENABLE_GLOBAL_JS_TS_SCAN", "ROUTE_ENABLE_BALANCED_CALL_SCANNER"]
            elif agent == "ServiceGraphAgent":
                candidates = ["SERVICE_ENABLE_CALL_ARGUMENT_CAPTURE", "SERVICE_ENABLE_IMPORT_FALLBACK_BY_STEM"]
            elif agent == "TestGenerationAgent":
                candidates = ["TEST_ENABLE_STATUS_ASSERTIONS", "TEST_ENABLE_RESPONSE_ASSERTIONS", "TEST_ENABLE_EXTRACTORS", "TEST_ENABLE_DATA_REFERENCES", "TEST_ENABLE_NEGATIVE_EDGE_TESTS"]
            else:
                candidates = []
            for c in candidates:
                if c not in seen and c in self.actions:
                    selected.append({"source":"deterministic_weak_agent_mapping","action":asdict(self.actions[c]),"confidence":0.85})
                    seen.add(c)
                    if len(selected) >= max_count:
                        return selected

        # Then map LLM deltas to safe patch actions.
        for d in llm_deltas or []:
            conf = float(d.get("confidence", 0.0) or 0.0)
            if conf < min_confidence:
                continue
            agent = d.get("agentName") or d.get("agent")
            intent = (d.get("patchIntent") or d.get("reason") or "").lower()
            candidates = self.allowed_for_agent(agent)
            for c in candidates:
                desc = (c["description"] + " " + c["action_id"]).lower()
                if any(tok in desc for tok in intent.split()[:8]):
                    aid = c["action_id"]
                    if aid not in seen:
                        selected.append({"source":"llm_delta_mapping","action":c,"confidence":conf,"llmDelta":d})
                        seen.add(aid)
                        break
            if len(selected) >= max_count:
                break
        return selected

def set_deep(d: Dict[str, Any], path: List[str], value: Any):
    cur = d
    for part in path[:-1]:
        cur = cur.setdefault(part, {})
    cur[path[-1]] = value

def snapshot_config(cfg):
    return copy.deepcopy(cfg)

def now():
    return datetime.datetime.utcnow().isoformat()+"Z"
