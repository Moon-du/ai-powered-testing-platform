from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrictRequestModel(BaseModel):
    """API command bodies reject unknown fields instead of silently discarding them."""

    model_config = ConfigDict(extra="forbid")


class AssetStatus(StrEnum):
    AI_DRAFT = "AI_DRAFT"
    HUMAN_EDITED = "HUMAN_EDITED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    STALE = "STALE"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ExpectedResultStatus(StrEnum):
    DEFINED = "DEFINED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


class GenerationMode(StrEnum):
    ALL = "ALL"
    SELECTED = "SELECTED"
    ADD_MORE = "ADD_MORE"


class ReviewAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class RejectionReason(StrEnum):
    INCORRECT = "INCORRECT"
    IRRELEVANT = "IRRELEVANT"
    DUPLICATE = "DUPLICATE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTS_WITH_KNOWLEDGE = "CONFLICTS_WITH_KNOWLEDGE"
    WRONG_GRANULARITY = "WRONG_GRANULARITY"
    OTHER = "OTHER"


class ConstraintSpec(BaseModel):
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    inclusive_minimum: bool = True
    inclusive_maximum: bool = True


class AssertionDraft(BaseModel):
    code: str
    text: str
    constraint: ConstraintSpec = Field(default_factory=ConstraintSpec)
    source_span: str


class AnalysisDraft(BaseModel):
    summary: str
    assertions: list[AssertionDraft] = Field(min_length=1)
    ambiguities: list[dict[str, Any]] = Field(default_factory=list)
    why_generated: str
    knowledge_reference_codes: list[str] = Field(default_factory=list)


class RiskDraft(BaseModel):
    code: str
    assertion_code: str
    title: str
    description: str
    likelihood: str
    impact: str
    rationale: str
    requirement_gap: bool = False
    why_generated: str
    knowledge_reference_codes: list[str] = Field(default_factory=list)


class ScenarioDraft(BaseModel):
    code: str
    risk_code: str
    title: str
    intent: str
    category: str
    preconditions: list[str] = Field(default_factory=list)
    expected_result: str | None = None
    expected_result_status: ExpectedResultStatus
    blocking_questions: list[str] = Field(default_factory=list)
    why_generated: str
    knowledge_reference_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_expected_result(self) -> "ScenarioDraft":
        if self.expected_result_status == ExpectedResultStatus.DEFINED:
            if not self.expected_result:
                raise ValueError("DEFINED scenarios require expected_result")
            if self.blocking_questions:
                raise ValueError("DEFINED scenarios cannot have blocking questions")
        elif self.expected_result is not None or not self.blocking_questions:
            raise ValueError(
                "CLARIFICATION_REQUIRED scenarios require null expected_result and questions"
            )
        return self


class StepDraft(BaseModel):
    sequence: int = Field(ge=1)
    action: str
    expected_result: str | None = None
    test_data: dict[str, Any] = Field(default_factory=dict)


class TestCaseDraft(BaseModel):
    code: str
    scenario_code: str
    title: str
    objective: str
    preconditions: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    expected_result: str | None = None
    expected_result_status: ExpectedResultStatus
    blocking_questions: list[str] = Field(default_factory=list)
    steps: list[StepDraft] = Field(min_length=1)
    why_generated: str
    knowledge_reference_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_expected_result(self) -> "TestCaseDraft":
        if self.expected_result_status == ExpectedResultStatus.DEFINED:
            if not self.expected_result or not self.expected_result.strip():
                raise ValueError("DEFINED cases require expected_result")
            if self.blocking_questions:
                raise ValueError("DEFINED cases cannot have blocking questions")
        elif self.expected_result is not None or not self.blocking_questions:
            raise ValueError(
                "CLARIFICATION_REQUIRED cases require null expected_result and questions"
            )
        return self


class ProductTypeRead(ORMModel):
    id: str
    tenant_id: str
    code: str
    name: str
    description: str


class KnowledgePackRead(ORMModel):
    id: str
    tenant_id: str
    product_type_id: str | None
    name: str
    version: str
    status: str
    description: str | None = None
    summary: dict[str, int] | None = None


class KnowledgeItemUpdate(BaseModel):
    item_type: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)
    parent_code: str | None = Field(default=None, max_length=80)


class KnowledgeItemRead(ORMModel):
    id: str
    item_type: str
    code: str
    title: str
    content: str
    parent_code: str | None


class KnowledgeContextRead(BaseModel):
    project_id: str
    knowledge_pack_id: str | None
    knowledge_pack_version: str | None
    knowledge_pack: KnowledgePackRead | None
    project_context: "ProjectContextRead"
    items: list[KnowledgeItemRead]
    item_counts: dict[str, int]
    summary: dict[str, int]
    counts: dict[str, int]
    modules: list[dict[str, Any]] = Field(default_factory=list)
    functions: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    failure_modes: list[dict[str, Any]] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    project_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    product_type_id: str | None = None
    product_type_code: str | None = None
    knowledge_pack_id: str | None = None
    knowledge_pack_version: str | None = None
    product_variant: str = ""
    project_version: str = "1.0"
    context_items: dict[str, Any] = Field(default_factory=dict)


class ProjectRead(ORMModel):
    id: str
    tenant_id: str
    project_code: str
    name: str
    description: str
    product_type_id: str | None
    product_type: ProductTypeRead | None = None
    knowledge_pack_id: str | None
    knowledge_pack_version: str | None
    product_variant: str
    project_version: str
    status: str
    owner: str
    context_revision: int = 1
    created_by: str
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    items: list[ProjectRead]


class ProductTypeList(BaseModel):
    items: list[ProductTypeRead]


class KnowledgePackList(BaseModel):
    items: list[KnowledgePackRead]


class ProjectMembershipCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern="^(OWNER|EDITOR|REVIEWER|VIEWER)$")


class ProjectMembershipRead(ORMModel):
    id: str
    tenant_id: str
    project_id: str
    user_id: str
    role: str
    created_at: datetime


class ProjectMembershipList(BaseModel):
    items: list[ProjectMembershipRead]


class ProjectContextRead(BaseModel):
    items: dict[str, Any]
    revision: int


class ProjectContextUpdate(BaseModel):
    items: dict[str, Any]
    expected_revision: int = Field(ge=1)


class RequirementCreate(BaseModel):
    requirement_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    original_text: str = Field(min_length=1)


class RequirementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    original_text: str | None = Field(default=None, min_length=1)
    change_summary: str = ""
    expected_revision: int = Field(ge=1)


class RequirementRead(ORMModel):
    id: str
    tenant_id: str
    project_id: str
    requirement_code: str
    title: str
    original_text: str
    revision: int
    semantic_hash: str
    created_at: datetime
    updated_at: datetime


class RequirementList(BaseModel):
    items: list[RequirementRead]


class RequirementRevisionRead(ORMModel):
    id: str
    requirement_id: str
    revision: int
    title: str
    original_text: str
    semantic_hash: str
    change_summary: str
    created_by: str
    created_at: datetime


class RequirementRevisionList(BaseModel):
    items: list[RequirementRevisionRead]


class AssertionRead(ORMModel):
    id: str
    requirement_id: str
    analysis_id: str
    code: str
    text: str
    constraint_json: dict[str, Any]
    source_span: str


class AnalysisRead(ORMModel):
    id: str
    project_id: str
    requirement_id: str
    source_requirement_revision: int
    asset_revision: int
    status: AssetStatus
    summary: str
    ambiguities_json: list[dict[str, Any]]
    why_generated: str
    rejection_reason: RejectionReason | None = None
    rejection_note: str | None = None
    supersedes_id: str | None
    created_at: datetime
    updated_at: datetime
    assertions: list[AssertionRead] = Field(default_factory=list)
    knowledge_references: list["KnowledgeReferenceRead"] = Field(default_factory=list)


class AnalysisReview(BaseModel):
    action: ReviewAction
    expected_revision: int = Field(ge=1)
    rejection_reason: RejectionReason | None = None
    rejection_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> "AnalysisReview":
        if self.action == ReviewAction.REJECT and self.rejection_reason is None:
            raise ValueError("rejection_reason is required when rejecting")
        return self


class AssertionUpdate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1)
    constraint_json: dict[str, Any] = Field(default_factory=dict)
    source_span: str = Field(min_length=1)


class AnalysisUpdate(BaseModel):
    summary: str | None = Field(default=None, min_length=1)
    ambiguities: list[dict[str, Any]] | None = None
    why_generated: str | None = Field(default=None, min_length=1)
    assertions: list[AssertionUpdate] | None = None
    expected_revision: int = Field(ge=1)


class AssetDelete(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class AnalysisOptions(StrictRequestModel):
    strict_grounding: bool = True
    include_questions: bool = True
    include_dependency_analysis: bool = True
    include_testability_analysis: bool = True
    language: str = Field(default="zh-CN", min_length=2, max_length=20)


class RiskGenerationOptions(StrictRequestModel):
    include_product_risks: bool = True
    include_failure_modes: bool = True
    include_dependency_risks: bool = True
    include_requirement_gaps: bool = True
    minimum_priority: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"


class ScenarioGenerationOptions(StrictRequestModel):
    include_nominal: bool = True
    include_boundary: bool = True
    include_negative: bool = True
    include_fault: bool = True
    include_recovery: bool = True
    include_persistence: bool = True
    include_interaction: bool = True
    include_regression: bool = True


class TestCaseGenerationOptions(StrictRequestModel):
    generation_strategy: Literal["ONE_OR_MORE_PER_SCENARIO"] = (
        "ONE_OR_MORE_PER_SCENARIO"
    )
    step_granularity: Literal["EXECUTION_READY"] = "EXECUTION_READY"
    include_preconditions: bool = True
    include_configuration: bool = True
    include_test_data: bool = True
    expected_result_per_step: bool = True
    avoid_unspecified_behavior: bool = True


class AnalyzeRequest(StrictRequestModel):
    project_id: str | None = None
    requirement_revision: int | None = Field(default=None, ge=1)
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)
    user_instruction: str | None = Field(default=None, max_length=4000)


class GenerateRequest(StrictRequestModel):
    mode: GenerationMode = GenerationMode.ALL
    selected_ids: list[str] = Field(default_factory=list)


class RiskGenerateRequest(StrictRequestModel):
    project_id: str | None = None
    requirement_id: str | None = None
    analysis_id: str
    mode: GenerationMode = GenerationMode.ALL
    assertion_ids: list[str] = Field(default_factory=list)
    options: RiskGenerationOptions = Field(default_factory=RiskGenerationOptions)


class ScenarioGenerateRequest(StrictRequestModel):
    project_id: str | None = None
    requirement_id: str | None = None
    analysis_id: str | None = None
    risk_batch_id: str
    mode: GenerationMode = GenerationMode.ALL
    risk_ids: list[str] | None = None
    risk_selection: list[str] | None = None
    options: ScenarioGenerationOptions = Field(
        default_factory=ScenarioGenerationOptions
    )

    @model_validator(mode="after")
    def reconcile_risk_selection(self) -> "ScenarioGenerateRequest":
        if (
            self.risk_ids is not None
            and self.risk_selection is not None
            and self.risk_ids != self.risk_selection
        ):
            raise ValueError("risk_ids and risk_selection must match when both are set")
        self.risk_ids = (
            self.risk_ids if self.risk_ids is not None else self.risk_selection or []
        )
        return self


class TestCaseGenerateRequest(StrictRequestModel):
    project_id: str | None = None
    requirement_id: str | None = None
    scenario_batch_id: str
    mode: GenerationMode = GenerationMode.ALL
    scenario_ids: list[str] = Field(default_factory=list)
    options: TestCaseGenerationOptions = Field(
        default_factory=TestCaseGenerationOptions
    )


class RunRead(ORMModel):
    id: str
    project_id: str
    requirement_id: str
    actor_id: str
    run_type: str
    status: RunStatus
    model: str
    input_json: dict[str, Any] = Field(default_factory=dict, exclude=True)
    result_type: str | None
    result_id: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @computed_field
    @property
    def task_type(self) -> str:
        return self.run_type

    @computed_field
    @property
    def result(self) -> dict[str, str] | None:
        if self.result_id is None or self.result_type is None:
            return None
        return {"type": self.result_type, "id": self.result_id}

    @computed_field
    @property
    def input_snapshot(self) -> dict[str, Any]:
        value = self.input_json.get("input_snapshot", {})
        if not isinstance(value, dict):
            return {}
        requirement = value.get("requirement", {})
        command = value.get("command", {})
        source = value.get("source")
        public_source: dict[str, Any] | None = None
        if isinstance(source, dict):
            selected = next(
                (
                    items
                    for key in ("assertions", "risks", "scenarios")
                    if isinstance((items := source.get(key)), list)
                ),
                [],
            )
            public_source = {
                "type": source.get("type"),
                "id": source.get("id"),
                "revision": source.get("revision", source.get("asset_revision")),
                "semantic_hash": source.get("semantic_hash"),
                "selected_asset_ids": [item.get("id") for item in selected],
                "selected_asset_revisions": {
                    item.get("id"): item.get("asset_revision")
                    for item in selected
                    if item.get("id") is not None
                },
                "selected_asset_semantic_hashes": {
                    item.get("id"): item.get("semantic_hash")
                    for item in selected
                    if item.get("id") is not None
                    and item.get("semantic_hash") is not None
                },
            }
        public = {
            "format_version": value.get("format_version"),
            "requirement": {
                "id": requirement.get("id"),
                "revision": requirement.get(
                    "revision", value.get("requirement_revision")
                ),
                "semantic_hash": requirement.get("semantic_hash"),
            },
            "requirement_revision": value.get("requirement_revision"),
            "knowledge_pack_id": value.get("knowledge_pack_id"),
            "knowledge_pack_version": value.get("knowledge_pack_version"),
            "knowledge_content_hash": value.get("knowledge_content_hash"),
            "project_context_revision": value.get("project_context_revision"),
            "project_context_hash": value.get("project_context_hash"),
            "command": {
                "mode": command.get("mode"),
                "selected_ids": command.get("selected_ids", []),
            },
            "source": public_source,
            "provider": value.get("provider"),
            "model": value.get("model"),
            "prompt_version": value.get("prompt_version"),
            "validator_version": value.get("validator_version"),
            "policy_version": value.get("policy_version"),
        }
        return public


class KnowledgeReferenceRead(ORMModel):
    id: str
    asset_type: str
    asset_id: str
    knowledge_item_id: str
    reference_code: str
    excerpt: str
    relevance: str


class RiskRead(ORMModel):
    id: str
    batch_id: str
    assertion_id: str
    code: str
    title: str
    description: str
    likelihood: str
    impact: str
    rationale: str
    requirement_gap: bool
    why_generated: str
    status: AssetStatus
    asset_revision: int
    rejection_reason: RejectionReason | None = None
    rejection_note: str | None = None
    knowledge_references: list[KnowledgeReferenceRead] = Field(default_factory=list)

    @computed_field
    @property
    def review_status(self) -> AssetStatus:
        return self.status


class RiskBatchRead(ORMModel):
    id: str
    project_id: str
    requirement_id: str
    source_analysis_id: str
    revision: int
    status: AssetStatus
    generation_mode: GenerationMode
    supersedes_id: str | None
    items: list[RiskRead] = Field(default_factory=list)

    @computed_field
    @property
    def review_status(self) -> AssetStatus:
        return self.status

    @computed_field
    @property
    def risks(self) -> list[RiskRead]:
        return self.items


class RiskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    likelihood: str | None = None
    impact: str | None = None
    rationale: str | None = Field(default=None, min_length=1)
    expected_revision: int = Field(ge=1)


class ScenarioRead(ORMModel):
    id: str
    batch_id: str
    risk_id: str
    code: str
    title: str
    intent: str
    category: str
    preconditions_json: list[str]
    expected_result: str | None
    expected_result_status: ExpectedResultStatus
    blocking_questions_json: list[str]
    why_generated: str
    status: AssetStatus
    asset_revision: int
    rejection_reason: RejectionReason | None = None
    rejection_note: str | None = None
    knowledge_references: list[KnowledgeReferenceRead] = Field(default_factory=list)

    @computed_field
    @property
    def review_status(self) -> AssetStatus:
        return self.status


class ScenarioBatchRead(ORMModel):
    id: str
    project_id: str
    requirement_id: str
    source_risk_batch_id: str
    revision: int
    status: AssetStatus
    generation_mode: GenerationMode
    supersedes_id: str | None
    items: list[ScenarioRead] = Field(default_factory=list)

    @computed_field
    @property
    def review_status(self) -> AssetStatus:
        return self.status

    @computed_field
    @property
    def scenarios(self) -> list[ScenarioRead]:
        return self.items


class ScenarioUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    intent: str | None = Field(default=None, min_length=1)
    category: str | None = None
    preconditions: list[str] | None = None
    expected_result: str | None = None
    expected_result_status: ExpectedResultStatus | None = None
    blocking_questions: list[str] | None = None
    expected_revision: int = Field(ge=1)


class TestStepRead(ORMModel):
    id: str
    sequence: int
    action: str
    expected_result: str | None
    test_data: dict[str, Any]


class TestCaseRead(ORMModel):
    id: str
    batch_id: str
    scenario_id: str
    code: str
    title: str
    objective: str
    preconditions_json: list[str]
    configuration_json: dict[str, Any]
    expected_result: str | None
    expected_result_status: ExpectedResultStatus
    blocking_questions_json: list[str]
    why_generated: str
    status: AssetStatus
    asset_revision: int
    rejection_reason: RejectionReason | None = None
    rejection_note: str | None = None
    steps: list[TestStepRead] = Field(default_factory=list)
    knowledge_references: list[KnowledgeReferenceRead] = Field(default_factory=list)

    @computed_field
    @property
    def review_status(self) -> AssetStatus:
        return self.status


class TestCaseBatchRead(ORMModel):
    id: str
    project_id: str
    requirement_id: str
    source_scenario_batch_id: str
    revision: int
    status: AssetStatus
    generation_mode: GenerationMode
    supersedes_id: str | None
    items: list[TestCaseRead] = Field(default_factory=list)

    @computed_field
    @property
    def review_status(self) -> AssetStatus:
        return self.status

    @computed_field
    @property
    def test_cases(self) -> list[TestCaseRead]:
        return self.items


class TestCaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    objective: str | None = Field(default=None, min_length=1)
    preconditions: list[str] | None = None
    configuration: dict[str, Any] | None = None
    expected_result: str | None = None
    expected_result_status: ExpectedResultStatus | None = None
    blocking_questions: list[str] | None = None
    steps: list["TestStepUpdate"] | None = None
    expected_revision: int = Field(ge=1)


class TestStepUpdate(BaseModel):
    action: str = Field(min_length=1)
    expected_result: str | None = None
    test_data: dict[str, Any] = Field(default_factory=dict)


class BatchReview(BaseModel):
    action: ReviewAction
    risk_ids: list[str] = Field(default_factory=list)
    scenario_ids: list[str] = Field(default_factory=list)
    test_case_ids: list[str] = Field(default_factory=list)
    expected_revisions: dict[str, int]
    rejection_reason: RejectionReason | None = None
    rejection_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> "BatchReview":
        if self.action == ReviewAction.REJECT and self.rejection_reason is None:
            raise ValueError("rejection_reason is required when rejecting")
        return self


class WorkflowRead(BaseModel):
    requirement: RequirementRead
    current_stage: str
    stages: list[dict[str, str]]
    active_assets: dict[str, Any]
    available_actions: list[str]
    runs: list[RunRead]
    blockers: list[dict[str, Any]]

    @computed_field
    @property
    def requirement_id(self) -> str:
        return self.requirement.id

    @computed_field
    @property
    def blocking_reasons(self) -> list[dict[str, Any]]:
        return self.blockers


class TraceabilityEdge(BaseModel):
    from_type: str
    from_id: str
    relation_type: str
    to_type: str
    to_id: str


class TraceabilityRead(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[TraceabilityEdge]


class RatioMetric(BaseModel):
    covered: int
    total: int
    percent: float


class CoverageRead(BaseModel):
    requirements: dict[str, int]
    assertions: RatioMetric
    risks: RatioMetric
    scenarios: dict[str, int]
    cases: dict[str, int]
    issues: dict[str, int]


AnalysisRead.model_rebuild()
KnowledgeContextRead.model_rebuild()
