from qaira_semantic_compiler.core.context import AgentResult

BODY_METHODS={"POST","PUT","PATCH"}

class InferredSchemaRegistryAgent:
    name="InferredSchemaRegistryAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        schemas=[]
        body_details={b["routeId"]:b for b in self.ctx.state.get("bodyDetails",[])}

        for route in self.ctx.state.get("routes",[]):
            body=route.get("requestBody")
            if not body:
                continue
            if route["method"] not in BODY_METHODS and not body_details.get(route["id"],{}).get("hasBody"):
                continue
            props=body.get("properties") or {}
            if not props:
                continue

            name=self.schema_name(route)
            schema={
                "name":name,
                "routeId":route["id"],
                "method":route["method"],
                "path":route["path"],
                "schema":{"type":"object","properties":props,"required":[]},
                "source":"precision_inferred_pattern_registry"
            }
            schemas.append(schema)
            body["schemaRef"]=name

        self.ctx.state["inferredSchemas"]=schemas
        self.ctx.write_json("validation/inferred_schema_registry.json",{
            "count":len(schemas),
            "items":schemas
        })
        return AgentResult(self.name,"success" if schemas else "failed_open",0.9 if schemas else 0.2,{"schemas":len(schemas)},{})

    def schema_name(self,route):
        parts=[p for p in route["path"].split("/") if p and not p.startswith(":") and not p.startswith("{")]
        base="".join(x.capitalize() for x in parts[-2:]) or "Root"
        return route["method"].capitalize()+base+"Request"
