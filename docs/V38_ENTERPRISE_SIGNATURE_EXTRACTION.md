# V38 Enterprise Signature Extraction

V37 found many functions but almost no useful parameter types.

V38 improves signature parsing for real-world TypeScript.

## Handles

```ts
function create(data: CreateDto) {}

const create = async (
  data: CreateDto
) => {}

const create: Handler<CreateDto> = async (data) => {}

async create(
  data: CreateDto,
  ctx: Context
) {}

save = (
  dto: Partial<User>
) => {}

save(dto?: SaveDto) {}

const save: ServiceHandler<CreateDto, ResponseDto> = async (dto) => {}
```

## Expected impact

The number that should improve is:

```text
typedFunctionSignatures
typeResolutions
type_resolved_import_aware_signature_dto_trace
bodyFieldsKnown
```

## Read after run

```text
validation/signature_extraction_diagnostics.json
validation/function_signature_registry.json
validation/type_resolution_report.json
validation/dto_trace_report.json
diagnostics/schema_resolution_diagnostics.json
```
