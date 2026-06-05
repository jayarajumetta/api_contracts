from qaira_semantic_compiler.core.context import AgentResult
import re

OPTIONAL_HINTS={"optional","nullable","maybe","partial"}
REQUIRED_HINTS={"required","must","mandatory"}

class RequiredFieldConfidenceAgent:
    name="RequiredFieldConfidenceAgent"

    def __init__(self, ctx, logger):
        self.ctx=ctx
        self.logger=logger

    def run(self):
        routes=self.ctx.state.get("routes",[])
        enriched=0
        items=[]

        for route in routes:
            body=route.get("requestBody")
            if not body:
                continue
            props=body.get("properties") or {}
            if not props:
                continue

            required=[]
            confidence_by_field={}

            for field in props.keys():
                score=0.55
                fname=field.lower()

                if fname in {"name","title","email","password","username","type","status"}:
                    score=0.82
                elif fname.endswith("id") or fname == "id":
                    score=0.75
                elif fname.startswith("is") or fname.startswith("has"):
                    score=0.60

                # Optional naming hints.
                if any(h in fname for h in OPTIONAL_HINTS):
                    score=0.25
                if any(h in fname for h in REQUIRED_HINTS):
                    score=0.90

                confidence_by_field[field]=round(score,2)

                if score >= 0.70:
                    required.append(field)

                props[field]["x-qaira-required-confidence"]=round(score,2)

            body["required"]=sorted(required)
            body["x-qaira-required-field-confidence"]=confidence_by_field
            enriched+=1
            items.append({
                "routeId":route["id"],
                "required":sorted(required),
                "confidenceByField":confidence_by_field
            })

        self.ctx.write_json("validation/required_field_confidence.json",{
            "enrichedRoutes":enriched,
            "items":items
        })
        return AgentResult(self.name,"success" if enriched else "failed_open",0.85 if enriched else 0.3,{"enrichedRoutes":enriched}, {})
