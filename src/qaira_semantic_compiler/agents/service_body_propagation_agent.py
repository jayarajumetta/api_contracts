from qaira_semantic_compiler.core.context import AgentResult

BODY_METHODS={"POST","PUT","PATCH"}

class ServiceBodyPropagationAgent:
    name="ServiceBodyPropagationAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        propagated=0
        items=[]

        service_fields=self.ctx.state.get("serviceBodyFieldsByRoute",{})
        db_fields=self.ctx.state.get("dbWriteFieldsByRoute",{})
        body_details={b["routeId"]:b for b in self.ctx.state.get("bodyDetails",[])}

        for route in self.ctx.state.get("routes",[]):
            rid=route["id"]
            body_known=bool(body_details.get(rid,{}).get("hasBody"))
            expects_body=route["method"] in BODY_METHODS

            # Do not attach request bodies to GET/DELETE/etc unless the handler explicitly used req.body.
            if not expects_body and not body_known:
                continue

            existing=set(((route.get("requestBody") or {}).get("properties") or {}).keys())
            merged=set(existing)
            merged.update(service_fields.get(rid,[]))
            merged.update(db_fields.get(rid,[]))

            if merged:
                route["requestBody"]={
                    "type":"object",
                    "properties":{f:{"type":"string","source":"precision_pattern_establishment"} for f in sorted(merged)},
                    "x-qaira-body-detected":True,
                    "x-qaira-fields-known":True,
                    "x-qaira-pattern-established":True
                }
                propagated+=1
                items.append({"routeId":rid,"method":route["method"],"path":route["path"],"fields":sorted(merged)})

        self.ctx.write_json("patterns/service_body_propagation.json",{
            "propagatedRoutes":propagated,
            "items":items
        })
        return AgentResult(self.name,"success" if propagated else "failed_open",0.85 if propagated else 0.3,{"propagatedRoutes":propagated}, {})
