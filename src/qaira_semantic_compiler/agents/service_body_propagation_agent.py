from qaira_semantic_compiler.core.context import AgentResult

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

        for route in self.ctx.state.get("routes",[]):
            rid=route["id"]
            existing=set(((route.get("requestBody") or {}).get("properties") or {}).keys())
            merged=set(existing)
            merged.update(service_fields.get(rid,[]))
            merged.update(db_fields.get(rid,[]))

            if merged:
                route["requestBody"]={
                    "type":"object",
                    "properties":{f:{"type":"string","source":"pattern_establishment"} for f in sorted(merged)},
                    "x-qaira-body-detected":True,
                    "x-qaira-fields-known":True,
                    "x-qaira-pattern-established":True
                }
                propagated+=1
                items.append({"routeId":rid,"fields":sorted(merged)})

        self.ctx.write_json("patterns/service_body_propagation.json",{
            "propagatedRoutes":propagated,
            "items":items
        })
        return AgentResult(self.name,"success" if propagated else "failed_open",0.85 if propagated else 0.3,{"propagatedRoutes":propagated}, {})
