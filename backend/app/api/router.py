from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from docx import Document
from fastapi import APIRouter, Body, Depends, File, Header, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.dependencies import Actor, get_current_actor, get_db
from app.errors import AppError
from app.repositories import DomainRepository
from app.schemas.domain import (
    AnalysisRead,
    AnalysisReview,
    AnalysisUpdate,
    AnalyzeRequest,
    BatchReview,
    AssetDelete,
    CoverageRead,
    GenerateRequest,
    GenerationMode,
    KnowledgeContextRead,
    KnowledgeItemUpdate,
    KnowledgePackList,
    KnowledgePackRead,
    ProjectContextRead,
    ProjectContextUpdate,
    ProjectCreate,
    ProjectList,
    ProjectMembershipCreate,
    ProjectMembershipList,
    ProjectMembershipRead,
    ProjectRead,
    ProductTypeList,
    RequirementCreate,
    RequirementList,
    RequirementRead,
    RequirementRevisionList,
    RequirementUpdate,
    RiskBatchRead,
    RiskGenerateRequest,
    RiskRead,
    RiskUpdate,
    RunRead,
    ScenarioBatchRead,
    ScenarioGenerateRequest,
    ScenarioRead,
    ScenarioUpdate,
    TestCaseBatchRead,
    TestCaseGenerateRequest,
    TestCaseRead,
    TestCaseUpdate,
    TraceabilityRead,
    WorkflowRead,
)
from app.services import WorkflowService

api_router = APIRouter()
ActorDep = Annotated[Actor, Depends(get_current_actor)]
DbDep = Annotated[Session, Depends(get_db)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def service(request: Request, db: Session) -> WorkflowService:
    return WorkflowService(
        DomainRepository(db),
        request.app.state.settings,
        gateway=request.app.state.llm_gateway,
    )


@api_router.get("/product-types", response_model=ProductTypeList)
def list_product_types(request: Request, actor: ActorDep, db: DbDep) -> ProductTypeList:
    return service(request, db).list_product_types(actor)


@api_router.get(
    "/product-types/{product_type_id}/knowledge-packs",
    response_model=KnowledgePackList,
)
def list_knowledge_packs(
    product_type_id: str, request: Request, actor: ActorDep, db: DbDep
) -> KnowledgePackList:
    return service(request, db).list_knowledge_packs(actor, product_type_id)


@api_router.get("/knowledge-packs/{knowledge_pack_id}", response_model=KnowledgePackRead)
def get_knowledge_pack(
    knowledge_pack_id: str, request: Request, actor: ActorDep, db: DbDep
) -> KnowledgePackRead:
    return service(request, db).get_knowledge_pack(actor, knowledge_pack_id)


@api_router.get("/projects", response_model=ProjectList)
def list_projects(request: Request, actor: ActorDep, db: DbDep) -> ProjectList:
    return service(request, db).list_projects(actor)


@api_router.post(
    "/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED
)
def create_project(
    payload: ProjectCreate, request: Request, actor: ActorDep, db: DbDep
) -> ProjectRead:
    return service(request, db).create_project(actor, payload)


@api_router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str, request: Request, actor: ActorDep, db: DbDep
) -> ProjectRead:
    return service(request, db).get_project(actor, project_id)


@api_router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str, request: Request, actor: ActorDep, db: DbDep
) -> None:
    service(request, db).delete_project(actor, project_id)


@api_router.get(
    "/projects/{project_id}/members", response_model=ProjectMembershipList
)
def list_project_members(
    project_id: str, request: Request, actor: ActorDep, db: DbDep
) -> ProjectMembershipList:
    return service(request, db).list_memberships(actor, project_id)


@api_router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    project_id: str,
    payload: ProjectMembershipCreate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> ProjectMembershipRead:
    return service(request, db).add_membership(actor, project_id, payload)


@api_router.get("/projects/{project_id}/context", response_model=ProjectContextRead)
def get_project_context(
    project_id: str, request: Request, actor: ActorDep, db: DbDep
) -> ProjectContextRead:
    return service(request, db).get_context(actor, project_id)


@api_router.get(
    "/projects/{project_id}/knowledge-context", response_model=KnowledgeContextRead
)
def get_project_knowledge_context(
    project_id: str, request: Request, actor: ActorDep, db: DbDep
) -> KnowledgeContextRead:
    return service(request, db).knowledge_context(actor, project_id)


@api_router.post("/projects/{project_id}/knowledge/files", response_model=KnowledgeContextRead)
async def upload_project_knowledge(
    project_id: str,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    files: list[UploadFile] = File(...),
    bump_version: bool = Query(False),
) -> KnowledgeContextRead:
    workflow = service(request, db)
    if len(files) > 10:
        raise AppError(422, "TOO_MANY_KNOWLEDGE_FILES", "每次最多上传 10 个文件。")
    additions = []
    for upload in files:
        raw = await upload.read()
        if len(raw) > 10 * 1024 * 1024:
            raise AppError(413, "KNOWLEDGE_FILE_TOO_LARGE", "单个文件不能超过 10 MB。")
        suffix = Path(upload.filename or "document").suffix.lower()
        try:
            if suffix in {".txt", ".md", ".markdown"}:
                content = raw.decode("utf-8-sig")
            elif suffix == ".docx":
                content = "\n".join(
                    paragraph.text
                    for paragraph in Document(BytesIO(raw)).paragraphs
                    if paragraph.text.strip()
                )
            elif (upload.content_type or "").startswith("image/"):
                content = workflow.gateway.extract_image_text(
                    raw, upload.content_type or "image/png"
                )
            else:
                raise AppError(
                    415,
                    "KNOWLEDGE_FILE_UNSUPPORTED",
                    "支持 TXT、Markdown、DOCX 和图片文件。",
                )
        except AppError:
            raise
        except (UnicodeDecodeError, ValueError, KeyError) as exc:
            raise AppError(
                422,
                "KNOWLEDGE_FILE_INVALID",
                f"无法读取文件 {upload.filename or 'document'}。",
            ) from exc
        if not content.strip():
            raise AppError(422, "KNOWLEDGE_FILE_EMPTY", "上传文件中没有可提取的文本。")
        additions.append({
            "item_type": "DOCUMENT",
            "code": f"DOC-{uuid4().hex[:12].upper()}",
            "title": upload.filename or "Document",
            "content": content.strip(),
            "parent_code": None,
            "metadata": {"source_filename": upload.filename, "content_type": upload.content_type},
        })
    return workflow.add_project_knowledge(actor, project_id, additions, bump_version)


@api_router.put("/projects/{project_id}/knowledge/items/{code}", response_model=KnowledgeContextRead)
def update_project_knowledge_item(
    project_id: str,
    code: str,
    payload: KnowledgeItemUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    bump_version: bool = Query(False),
) -> KnowledgeContextRead:
    return service(request, db).update_project_knowledge(
        actor, project_id, code, payload, bump_version
    )


@api_router.delete("/projects/{project_id}/knowledge/items/{code}", response_model=KnowledgeContextRead)
def delete_project_knowledge_item(
    project_id: str,
    code: str,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    bump_version: bool = Query(False),
) -> KnowledgeContextRead:
    return service(request, db).delete_project_knowledge(actor, project_id, code, bump_version)


@api_router.put("/projects/{project_id}/context", response_model=ProjectContextRead)
def update_project_context(
    project_id: str,
    payload: ProjectContextUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> ProjectContextRead:
    return service(request, db).update_context(actor, project_id, payload)


@api_router.get(
    "/projects/{project_id}/requirements", response_model=RequirementList
)
def list_requirements(
    project_id: str, request: Request, actor: ActorDep, db: DbDep
) -> RequirementList:
    return service(request, db).list_requirements(actor, project_id)


@api_router.post(
    "/projects/{project_id}/requirements",
    response_model=RequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_requirement(
    project_id: str,
    payload: RequirementCreate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> RequirementRead:
    return service(request, db).create_requirement(actor, project_id, payload)


@api_router.get("/requirements/{requirement_id}", response_model=RequirementRead)
def get_requirement(
    requirement_id: str, request: Request, actor: ActorDep, db: DbDep
) -> RequirementRead:
    return service(request, db).get_requirement(actor, requirement_id)


@api_router.get(
    "/requirements/{requirement_id}/revisions", response_model=RequirementRevisionList
)
def get_requirement_revisions(
    requirement_id: str, request: Request, actor: ActorDep, db: DbDep
) -> RequirementRevisionList:
    return service(request, db).requirement_revisions(actor, requirement_id)


@api_router.patch("/requirements/{requirement_id}", response_model=RequirementRead)
def update_requirement(
    requirement_id: str,
    payload: RequirementUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> RequirementRead:
    return service(request, db).update_requirement(actor, requirement_id, payload)


@api_router.post(
    "/requirements/{requirement_id}/analyze",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_requirement(
    requirement_id: str,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    payload: AnalyzeRequest = Body(default_factory=AnalyzeRequest),
    idempotency_key: IdempotencyKey = None,
) -> RunRead:
    return service(request, db).start_analysis(
        actor, requirement_id, idempotency_key, payload
    )


@api_router.get("/analyses/{analysis_id}", response_model=AnalysisRead)
def get_analysis(
    analysis_id: str, request: Request, actor: ActorDep, db: DbDep
) -> AnalysisRead:
    return service(request, db).get_analysis(actor, analysis_id)


@api_router.get(
    "/requirements/{requirement_id}/analyses/{analysis_id}", response_model=AnalysisRead
)
def get_requirement_analysis(
    requirement_id: str,
    analysis_id: str,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> AnalysisRead:
    return service(request, db).get_analysis_for_requirement(
        actor, requirement_id, analysis_id
    )


@api_router.post("/analyses/{analysis_id}/review", response_model=AnalysisRead)
def review_analysis(
    analysis_id: str,
    payload: AnalysisReview,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> AnalysisRead:
    return service(request, db).review_analysis(actor, analysis_id, payload)


@api_router.patch("/analyses/{analysis_id}", response_model=AnalysisRead)
def update_analysis(
    analysis_id: str, payload: AnalysisUpdate, request: Request, actor: ActorDep, db: DbDep
) -> AnalysisRead:
    return service(request, db).update_analysis(actor, analysis_id, payload)


@api_router.delete("/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(
    analysis_id: str, payload: AssetDelete, request: Request, actor: ActorDep, db: DbDep
) -> None:
    service(request, db).delete_analysis(actor, analysis_id, payload)


@api_router.patch(
    "/requirements/{requirement_id}/analyses/{analysis_id}/review",
    response_model=AnalysisRead,
)
def review_requirement_analysis(
    requirement_id: str,
    analysis_id: str,
    payload: AnalysisReview,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> AnalysisRead:
    return service(request, db).review_analysis_for_requirement(
        actor, requirement_id, analysis_id, payload
    )


@api_router.post(
    "/analyses/{analysis_id}/risks/generate",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_risks(
    analysis_id: str,
    payload: GenerateRequest,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    idempotency_key: IdempotencyKey = None,
) -> RunRead:
    return service(request, db).start_risks(
        actor, analysis_id, payload, idempotency_key
    )


@api_router.post(
    "/risks/generate", response_model=RunRead, status_code=status.HTTP_202_ACCEPTED
)
def generate_risks_canonical(
    payload: RiskGenerateRequest,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    idempotency_key: IdempotencyKey = None,
) -> RunRead:
    mode = (
        GenerationMode.SELECTED
        if payload.assertion_ids and payload.mode == GenerationMode.ALL
        else payload.mode
    )
    return service(request, db).start_risks(
        actor,
        payload.analysis_id,
        GenerateRequest(mode=mode, selected_ids=payload.assertion_ids),
        idempotency_key,
        project_id=payload.project_id,
        requirement_id=payload.requirement_id,
        options=payload.options.model_dump(),
    )


@api_router.get("/risk-batches/{batch_id}", response_model=RiskBatchRead)
def get_risk_batch(
    batch_id: str, request: Request, actor: ActorDep, db: DbDep
) -> RiskBatchRead:
    return service(request, db).get_risk_batch(actor, batch_id)


@api_router.patch("/risks/{risk_id}", response_model=RiskRead)
def update_risk(
    risk_id: str,
    payload: RiskUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> RiskRead:
    return service(request, db).update_risk(actor, risk_id, payload)


@api_router.delete("/risks/{risk_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_risk(
    risk_id: str, payload: AssetDelete, request: Request, actor: ActorDep, db: DbDep
) -> None:
    service(request, db).delete_risk(actor, risk_id, payload)


@api_router.patch("/risk-batches/{batch_id}/risks/{risk_id}", response_model=RiskRead)
def update_batch_risk(
    batch_id: str,
    risk_id: str,
    payload: RiskUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> RiskRead:
    return service(request, db).update_risk_in_batch(actor, batch_id, risk_id, payload)


@api_router.post("/risk-batches/{batch_id}/review", response_model=RiskBatchRead)
def review_risk_batch(
    batch_id: str,
    payload: BatchReview,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> RiskBatchRead:
    return service(request, db).review_risk_batch(actor, batch_id, payload)


@api_router.post(
    "/risk-batches/{batch_id}/scenarios/generate",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_scenarios(
    batch_id: str,
    payload: GenerateRequest,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    idempotency_key: IdempotencyKey = None,
) -> RunRead:
    return service(request, db).start_scenarios(
        actor, batch_id, payload, idempotency_key
    )


@api_router.post(
    "/scenarios/generate",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_scenarios_canonical(
    payload: ScenarioGenerateRequest,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    idempotency_key: IdempotencyKey = None,
) -> RunRead:
    selected = payload.risk_ids or []
    mode = (
        GenerationMode.SELECTED
        if selected and payload.mode == GenerationMode.ALL
        else payload.mode
    )
    return service(request, db).start_scenarios(
        actor,
        payload.risk_batch_id,
        GenerateRequest(mode=mode, selected_ids=selected),
        idempotency_key,
        project_id=payload.project_id,
        requirement_id=payload.requirement_id,
        analysis_id=payload.analysis_id,
        options=payload.options.model_dump(),
    )


@api_router.get("/scenario-batches/{batch_id}", response_model=ScenarioBatchRead)
def get_scenario_batch(
    batch_id: str, request: Request, actor: ActorDep, db: DbDep
) -> ScenarioBatchRead:
    return service(request, db).get_scenario_batch(actor, batch_id)


@api_router.patch("/scenarios/{scenario_id}", response_model=ScenarioRead)
def update_scenario(
    scenario_id: str,
    payload: ScenarioUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> ScenarioRead:
    return service(request, db).update_scenario(actor, scenario_id, payload)


@api_router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(
    scenario_id: str, payload: AssetDelete, request: Request, actor: ActorDep, db: DbDep
) -> None:
    service(request, db).delete_scenario(actor, scenario_id, payload)


@api_router.patch(
    "/scenario-batches/{batch_id}/scenarios/{scenario_id}",
    response_model=ScenarioRead,
)
def update_batch_scenario(
    batch_id: str,
    scenario_id: str,
    payload: ScenarioUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> ScenarioRead:
    return service(request, db).update_scenario_in_batch(
        actor, batch_id, scenario_id, payload
    )


@api_router.post(
    "/scenario-batches/{batch_id}/review", response_model=ScenarioBatchRead
)
def review_scenario_batch(
    batch_id: str,
    payload: BatchReview,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> ScenarioBatchRead:
    return service(request, db).review_scenario_batch(actor, batch_id, payload)


@api_router.post(
    "/scenario-batches/{batch_id}/test-cases/generate",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_test_cases(
    batch_id: str,
    payload: GenerateRequest,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    idempotency_key: IdempotencyKey = None,
) -> RunRead:
    return service(request, db).start_test_cases(
        actor, batch_id, payload, idempotency_key
    )


@api_router.post(
    "/testcases/generate",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_test_cases_canonical(
    payload: TestCaseGenerateRequest,
    request: Request,
    actor: ActorDep,
    db: DbDep,
    idempotency_key: IdempotencyKey = None,
) -> RunRead:
    mode = (
        GenerationMode.SELECTED
        if payload.scenario_ids and payload.mode == GenerationMode.ALL
        else payload.mode
    )
    return service(request, db).start_test_cases(
        actor,
        payload.scenario_batch_id,
        GenerateRequest(mode=mode, selected_ids=payload.scenario_ids),
        idempotency_key,
        project_id=payload.project_id,
        requirement_id=payload.requirement_id,
        options=payload.options.model_dump(),
    )


@api_router.get("/test-case-batches/{batch_id}", response_model=TestCaseBatchRead)
def get_test_case_batch(
    batch_id: str, request: Request, actor: ActorDep, db: DbDep
) -> TestCaseBatchRead:
    return service(request, db).get_test_case_batch(actor, batch_id)


@api_router.get("/testcase-batches/{batch_id}", response_model=TestCaseBatchRead)
def get_testcase_batch_alias(
    batch_id: str, request: Request, actor: ActorDep, db: DbDep
) -> TestCaseBatchRead:
    return service(request, db).get_test_case_batch(actor, batch_id)


@api_router.patch("/test-cases/{test_case_id}", response_model=TestCaseRead)
def update_test_case(
    test_case_id: str,
    payload: TestCaseUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> TestCaseRead:
    return service(request, db).update_test_case(actor, test_case_id, payload)


@api_router.delete("/test-cases/{test_case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_case(
    test_case_id: str, payload: AssetDelete, request: Request, actor: ActorDep, db: DbDep
) -> None:
    service(request, db).delete_test_case(actor, test_case_id, payload)


@api_router.patch(
    "/testcase-batches/{batch_id}/testcases/{test_case_id}",
    response_model=TestCaseRead,
)
def update_batch_test_case(
    batch_id: str,
    test_case_id: str,
    payload: TestCaseUpdate,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> TestCaseRead:
    return service(request, db).update_test_case_in_batch(
        actor, batch_id, test_case_id, payload
    )


@api_router.post(
    "/test-case-batches/{batch_id}/review", response_model=TestCaseBatchRead
)
def review_test_case_batch(
    batch_id: str,
    payload: BatchReview,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> TestCaseBatchRead:
    return service(request, db).review_test_case_batch(actor, batch_id, payload)


@api_router.post("/testcase-batches/{batch_id}/review", response_model=TestCaseBatchRead)
def review_testcase_batch_alias(
    batch_id: str,
    payload: BatchReview,
    request: Request,
    actor: ActorDep,
    db: DbDep,
) -> TestCaseBatchRead:
    return service(request, db).review_test_case_batch(actor, batch_id, payload)


@api_router.get("/ai-runs/{run_id}", response_model=RunRead)
def get_ai_run(
    run_id: str, request: Request, actor: ActorDep, db: DbDep
) -> RunRead:
    return service(request, db).get_run(actor, run_id)


@api_router.get(
    "/requirements/{requirement_id}/workflow", response_model=WorkflowRead
)
def get_workflow(
    requirement_id: str, request: Request, actor: ActorDep, db: DbDep
) -> WorkflowRead:
    return service(request, db).workflow(actor, requirement_id)


@api_router.get(
    "/projects/{project_id}/traceability", response_model=TraceabilityRead
)
def get_traceability(
    project_id: str, request: Request, actor: ActorDep, db: DbDep
) -> TraceabilityRead:
    return service(request, db).traceability(actor, project_id)


@api_router.get(
    "/requirements/{requirement_id}/traceability", response_model=TraceabilityRead
)
def get_requirement_traceability(
    requirement_id: str, request: Request, actor: ActorDep, db: DbDep
) -> TraceabilityRead:
    return service(request, db).requirement_traceability(actor, requirement_id)


@api_router.get("/projects/{project_id}/coverage", response_model=CoverageRead)
def get_coverage(
    project_id: str, request: Request, actor: ActorDep, db: DbDep
) -> CoverageRead:
    return service(request, db).coverage(actor, project_id)
