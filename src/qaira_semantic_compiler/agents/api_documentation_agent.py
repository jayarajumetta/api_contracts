from qaira_semantic_compiler.core.context import AgentResult
import json

class ApiDocumentationAgent:
    name = "ApiDocumentationAgent"

    def __init__(self, ctx, logger):
        self.ctx = ctx
        self.logger = logger

    def run(self):
        contracts = self.ctx.state.get("contracts") or (self.ctx.read_json("discovery/unified_api_contracts.json", {}) or {}).get("contracts", [])
        docs = []
        docs.append("# Generated API Documentation")
        docs.append("")
        docs.append("This document was generated from source-code analysis. It includes endpoint references, parameters, payloads, inferred schemas, examples, and generated test references.")
        docs.append("")
        docs.append("## Summary")
        summary = self.ctx.read_json("summary/scan_summary.json", {}) or {}
        docs.append("")
        docs.append("| Metric | Value |")
        docs.append("|---|---:|")
        for k in ["apiContracts","bodyExpected","bodyDetected","bodyFieldsKnown","pathParamsDiscovered","queryParamsDiscovered","serviceEdges","inferredSchemas"]:
            if k in summary:
                docs.append(f"| {k} | {summary[k]} |")

        grouped = {}
        for c in contracts:
            group = self.group_name(c.get("path","/"))
            grouped.setdefault(group, []).append(c)

        for group, items in sorted(grouped.items()):
            docs.append("")
            docs.append(f"## {group}")
            for c in sorted(items, key=lambda x: (x.get("path",""), x.get("method",""))):
                docs += self.endpoint_doc(c)

        text = "\n".join(docs) + "\n"
        self.ctx.write_text("docs/API_REFERENCE.md", text)
        self.ctx.write_json("docs/api_reference_index.json", {"groups": {k: len(v) for k,v in grouped.items()}, "contracts": len(contracts)})
        return AgentResult(self.name, "success", 0.95 if contracts else 0.0, {"contractsDocumented": len(contracts)}, {"file": "docs/API_REFERENCE.md"})

    def group_name(self, path):
        parts = [p for p in path.split("/") if p and not p.startswith(":") and not p.startswith("{")]
        return parts[0].capitalize() if parts else "Root"

    def endpoint_doc(self, c):
        out = []
        method = c.get("method")
        path = c.get("path")
        out.append("")
        out.append(f"### `{method} {path}`")
        out.append("")
        out.append(f"- Source: `{c.get('file','')}` line `{c.get('line','')}`")
        out.append(f"- Confidence: `{c.get('confidence','')}`")

        params = c.get("parameters") or []
        if params:
            out.append("")
            out.append("#### Parameters")
            out.append("")
            out.append("| Name | In | Type | Required |")
            out.append("|---|---|---|---|")
            for p in params:
                out.append(f"| `{p.get('name')}` | `{p.get('in')}` | `{p.get('type','string')}` | `{str(p.get('required', p.get('in')=='path')).lower()}` |")

        body = c.get("requestBody")
        if body:
            out.append("")
            out.append("#### Request payload")
            out.append("")
            out.append(f"- Schema ref: `{body.get('schemaRef') or body.get('declaredSchemaRef') or 'inline'}`")
            props = body.get("properties") or {}
            required = set(body.get("required") or [])
            if props:
                out.append("")
                out.append("| Field | Type | Required | Source |")
                out.append("|---|---|---|---|")
                for name, meta in props.items():
                    out.append(f"| `{name}` | `{meta.get('type','string')}` | `{str(name in required).lower()}` | `{meta.get('source','inferred')}` |")
                out.append("")
                out.append("Example:")
                out.append("")
                out.append("```json")
                out.append(json.dumps({k: self.example_value(k) for k in props.keys()}, indent=2))
                out.append("```")

        out.append("")
        out.append("#### Test references")
        out.append("")
        out.append("- Postman: `generated/postman_collection.json`")
        out.append("- Negative tests: `generated/negative_tests.postman_collection.json`")
        out.append("- Edge tests: `generated/edge_tests.postman_collection.json`")
        return out

    def example_value(self, name):
        n = name.lower()
        if "email" in n:
            return "user@example.com"
        if "password" in n:
            return "Password@123"
        if n.endswith("id") or n == "id":
            return "sample-id"
        if n.startswith("is") or n.startswith("has"):
            return True
        if "count" in n or "page" in n or "limit" in n:
            return 1
        return "sample"
