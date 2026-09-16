from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.ai import DomainValidator, LLMGateway, build_llm_gateway
from app.config import Settings
from app.dependencies import Actor
from app.errors import AppError, gate_blocked, version_conflict
from app.models import (
    AIRun,
    Analysis,
    AssetRelation,
    KnowledgeReference,
    KnowledgeItem,
    KnowledgePack,
    Project,
    ProjectContext,
    ProjectMembership,
    Requirement,
    RequirementAssertion,
    RequirementRevision,
    Risk,
    RiskBatch,
    Scenario,
    ScenarioBatch,
    TestCase,
    TestCaseBatch,
    TestStep,
)
from app.repositories import DomainRepository
from app.schemas.domain import (
    AnalysisDraft,
    AnalysisRead,
    AnalysisReview,
    AnalysisUpdate,
    AnalyzeRequest,
    AssertionDraft,
    AssertionRead,
    AssetStatus,
    AssetDelete,
    BatchReview,
    CoverageRead,
    ExpectedResultStatus,
    GenerateRequest,
    GenerationMode,
    KnowledgeReferenceRead,
    KnowledgeContextRead,
    KnowledgeItemRead,
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
    ProductTypeRead,
    RatioMetric,
    RequirementCreate,
    RequirementList,
    RequirementRead,
    RequirementRevisionList,
    RequirementRevisionRead,
    RequirementUpdate,
    ReviewAction,
    RiskBatchRead,
    RiskDraft,
    RiskRead,
    RiskUpdate,
    RunRead,
    RunStatus,
    ScenarioBatchRead,
    ScenarioDraft,
    ScenarioRead,
    ScenarioUpdate,
    StepDraft,
    TestCaseBatchRead,
    TestCaseDraft,
    TestCaseRead,
    TestCaseUpdate,
    TestStepRead,
    TraceabilityEdge,
    TraceabilityRead,
    WorkflowRead,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def semantic_hash(*values: Any) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.casefold().encode("utf-8")).hexdigest()


def risk_semantic_hash(item: Any) -> str:
    return semantic_hash(
        item.code,
        item.title,
        item.description,
        item.likelihood,
        item.impact,
        item.rationale,
        item.requirement_gap,
        item.why_generated,
    )


def scenario_semantic_hash(item: Any) -> str:
    preconditions = getattr(item, "preconditions_json", None)
    if preconditions is None:
        preconditions = item.preconditions
    questions = getattr(item, "blocking_questions_json", None)
    if questions is None:
        questions = item.blocking_questions
    return semantic_hash(
        item.code,
        item.title,
        item.intent,
        item.category,
        preconditions,
        item.expected_result,
        item.expected_result_status,
        questions,
        item.why_generated,
    )


def test_case_semantic_hash(item: Any) -> str:
    preconditions = getattr(item, "preconditions_json", None)
    if preconditions is None:
        preconditions = item.preconditions
    configuration = getattr(item, "configuration_json", None)
    if configuration is None:
        configuration = item.configuration
    questions = getattr(item, "blocking_questions_json", None)
    if questions is None:
        questions = item.blocking_questions
    return semantic_hash(
        item.code,
        item.title,
        item.objective,
        preconditions,
        configuration,
        item.expected_result,
        item.expected_result_status,
        questions,
        item.why_generated,
    )


class ContextBuilder:
    def __init__(self, repository: DomainRepository) -> None:
        self.repository = repository

    def build(self, tenant_id: str, requirement: Requirement) -> tuple[Project, dict[str, str]]:
        project = self.repository.project_internal(tenant_id, requirement.project_id)
        return project, {}


class KnowledgeRetriever:
    """P0 deterministic structured retrieval; replaceable by hybrid/vector retrieval."""

    def __init__(self, repository: DomainRepository) -> None:
        self.repository = repository

    def retrieve(self, tenant_id: str, project: Project) -> dict[str, str]:
        if not project.knowledge_pack_id:
            return {}
        return {
            item.code: item.content
            for item in self.repository.knowledge_items(
                tenant_id, project.knowledge_pack_id
            )
        }


class WorkflowService:
    def __init__(
        self,
        repository: DomainRepository,
        settings: Settings,
        gateway: LLMGateway | None = None,
    ) -> None:
        self.repo = repository
        self.settings = settings
        self.gateway = gateway or build_llm_gateway(settings)
        self.context_builder = ContextBuilder(repository)
        self.retriever = KnowledgeRetriever(repository)

    # Project and immutable requirement boundaries
    def list_projects(self, actor: Actor) -> ProjectList:
        return ProjectList(
            items=[self._project_read(actor, item) for item in self.repo.list_projects(actor)]
        )

    def list_product_types(self, actor: Actor) -> ProductTypeList:
        return ProductTypeList(
            items=[
                ProductTypeRead.model_validate(item)
                for item in self.repo.list_product_types(actor.tenant_id)
            ]
        )

    def list_knowledge_packs(
        self, actor: Actor, product_type_id: str
    ) -> KnowledgePackList:
        product = next(
            (
                item
                for item in self.repo.list_product_types(actor.tenant_id)
                if item.id == product_type_id
            ),
            None,
        )
        if product is None:
            from app.errors import not_found

            raise not_found("ProductType", product_type_id)
        return KnowledgePackList(
            items=[
                self._pack_read(actor.tenant_id, item)
                for item in self.repo.list_knowledge_packs(
                    actor.tenant_id, product_type_id
                )
            ]
        )

    def get_knowledge_pack(
        self, actor: Actor, knowledge_pack_id: str
    ) -> KnowledgePackRead:
        return self._pack_read(
            actor.tenant_id,
            self.repo.knowledge_pack_by_id(actor.tenant_id, knowledge_pack_id),
        )

    def create_project(self, actor: Actor, data: ProjectCreate) -> ProjectRead:
        product = None
        if data.product_type_id:
            product = self.repo.product_type_by_id(
                actor.tenant_id, data.product_type_id
            )
        elif data.product_type_code:
            product = self.repo.product_type(
                actor.tenant_id,
                data.product_type_code,
            )
        if data.product_type_code and product and data.product_type_code != product.code:
            raise AppError(
                422,
                "PRODUCT_TYPE_MISMATCH",
                "product_type_id and product_type_code identify different products.",
            )
        pack = None
        if data.knowledge_pack_id:
            pack = self.repo.knowledge_pack_by_id(
                actor.tenant_id, data.knowledge_pack_id
            )
            if (
                (product and pack.product_type_id not in (None, product.id))
                or (data.knowledge_pack_version and pack.version != data.knowledge_pack_version)
            ):
                raise AppError(
                    422,
                    "KNOWLEDGE_PACK_MISMATCH",
                    "The selected pack does not match the product type and version.",
                )
        project = self.repo.add(
            Project(
                tenant_id=actor.tenant_id,
                project_code=data.project_code,
                name=data.name,
                description=data.description,
                product_type_id=product.id if product else pack.product_type_id if pack else None,
                knowledge_pack_id=pack.id if pack else None,
                knowledge_pack_version=pack.version if pack else None,
                product_variant=data.product_variant,
                project_version=data.project_version,
                status="ACTIVE",
                owner=actor.user_id,
                created_by=actor.user_id,
            )
        )
        self.repo.flush()
        self.repo.add_all(
            [
                ProjectContext(
                    tenant_id=actor.tenant_id,
                    project_id=project.id,
                    summary="",
                    constraints_json=data.context_items,
                ),
                ProjectMembership(
                    tenant_id=actor.tenant_id,
                    project_id=project.id,
                    user_id=actor.user_id,
                    role="OWNER",
                ),
            ]
        )
        self.repo.flush()
        return self._project_read(actor, project)

    def get_project(self, actor: Actor, project_id: str) -> ProjectRead:
        return self._project_read(actor, self.repo.require_project(actor, project_id))

    def delete_project(self, actor: Actor, project_id: str) -> None:
        self._require_role(actor, project_id, {"OWNER"})
        project = self.repo.require_project(actor, project_id)
        private_pack = None
        if project.knowledge_pack_id:
            pack = self.repo.knowledge_pack_by_id(
                actor.tenant_id, project.knowledge_pack_id
            )
            if pack.status == "PROJECT_PRIVATE":
                private_pack = pack
                project.knowledge_pack_id = None
                project.knowledge_pack_version = None
                self.repo.flush()
        self.repo.delete(project)
        self.repo.flush()
        if private_pack is not None:
            self.repo.delete(private_pack)
            self.repo.flush()

    def list_memberships(
        self, actor: Actor, project_id: str
    ) -> ProjectMembershipList:
        return ProjectMembershipList(
            items=[
                ProjectMembershipRead.model_validate(item)
                for item in self.repo.memberships(actor, project_id)
            ]
        )

    def add_membership(
        self, actor: Actor, project_id: str, data: ProjectMembershipCreate
    ) -> ProjectMembershipRead:
        self._require_role(actor, project_id, {"OWNER"})
        existing = next(
            (
                item
                for item in self.repo.memberships(actor, project_id)
                if item.user_id == data.user_id
            ),
            None,
        )
        if existing is not None:
            return ProjectMembershipRead.model_validate(existing)
        membership = self.repo.add(
            ProjectMembership(
                tenant_id=actor.tenant_id,
                project_id=project_id,
                user_id=data.user_id,
                role=data.role,
            )
        )
        self.repo.flush()
        return ProjectMembershipRead.model_validate(membership)

    def get_context(self, actor: Actor, project_id: str) -> ProjectContextRead:
        context = self.repo.project_context(actor, project_id)
        return ProjectContextRead(items=context.constraints_json, revision=context.revision)

    def knowledge_context(
        self, actor: Actor, project_id: str
    ) -> KnowledgeContextRead:
        project = self.repo.require_project(actor, project_id)
        context = self.repo.project_context(actor, project_id)
        if not project.knowledge_pack_id:
            return KnowledgeContextRead(
                project_id=project.id,
                knowledge_pack_id=None,
                knowledge_pack_version=None,
                knowledge_pack=None,
                project_context=ProjectContextRead(
                    items=context.constraints_json, revision=context.revision
                ),
                items=[],
                item_counts={},
                summary={},
                counts={},
            )
        pack = self.repo.knowledge_pack_by_id(
            actor.tenant_id, project.knowledge_pack_id
        )
        items = self.repo.knowledge_items(actor.tenant_id, pack.id)
        counts: dict[str, int] = {}
        for item in items:
            counts[item.item_type] = counts.get(item.item_type, 0) + 1
        serialized = [
            {"id": item.id, "code": item.code, "title": item.title, "content": item.content}
            for item in items
        ]
        by_type = lambda *types: [
            value
            for value, item in zip(serialized, items, strict=True)
            if item.item_type in types
        ]
        return KnowledgeContextRead(
            project_id=project.id,
            knowledge_pack_id=pack.id,
            knowledge_pack_version=pack.version,
            knowledge_pack=self._pack_read(actor.tenant_id, pack),
            project_context=ProjectContextRead(
                items=context.constraints_json, revision=context.revision
            ),
            items=[KnowledgeItemRead.model_validate(item) for item in items],
            item_counts=counts,
            summary=counts,
            counts=counts,
            modules=by_type("MODULE"),
            functions=by_type("FUNCTION", "DEPENDENCY"),
            risks=by_type("RISK_PATTERN", "FAILURE_MODE"),
            rules=by_type("TESTING_RULE"),
            patterns=by_type("RISK_PATTERN"),
            failure_modes=by_type("FAILURE_MODE"),
        )

    def add_project_knowledge(
        self,
        actor: Actor,
        project_id: str,
        additions: list[dict[str, Any]],
        bump_version: bool,
    ) -> KnowledgeContextRead:
        return self._replace_project_knowledge(
            actor, project_id, additions=additions, bump_version=bump_version
        )

    def update_project_knowledge(
        self,
        actor: Actor,
        project_id: str,
        code: str,
        data: KnowledgeItemUpdate,
        bump_version: bool,
    ) -> KnowledgeContextRead:
        return self._replace_project_knowledge(
            actor,
            project_id,
            update_code=code,
            update_data=data,
            bump_version=bump_version,
        )

    def delete_project_knowledge(
        self, actor: Actor, project_id: str, code: str, bump_version: bool
    ) -> KnowledgeContextRead:
        return self._replace_project_knowledge(
            actor, project_id, delete_code=code, bump_version=bump_version
        )

    def _replace_project_knowledge(
        self,
        actor: Actor,
        project_id: str,
        *,
        additions: list[dict[str, Any]] | None = None,
        update_code: str | None = None,
        update_data: KnowledgeItemUpdate | None = None,
        delete_code: str | None = None,
        bump_version: bool,
    ) -> KnowledgeContextRead:
        self._require_role(actor, project_id, {"OWNER", "EDITOR", "REVIEWER"})
        project = self.repo.require_project(actor, project_id)
        old_pack = (
            self.repo.knowledge_pack_by_id(actor.tenant_id, project.knowledge_pack_id)
            if project.knowledge_pack_id
            else None
        )
        items = [
            {
                "item_type": item.item_type,
                "code": item.code,
                "title": item.title,
                "content": item.content,
                "parent_code": item.parent_code,
                "metadata": item.metadata_json,
            }
            for item in (
                self.repo.knowledge_items(actor.tenant_id, old_pack.id) if old_pack else []
            )
        ]
        if update_code:
            target = next((item for item in items if item["code"] == update_code), None)
            if target is None:
                from app.errors import not_found
                raise not_found("KnowledgeItem", update_code)
            assert update_data is not None
            target.update(update_data.model_dump())
        if delete_code:
            remaining = [item for item in items if item["code"] != delete_code]
            if len(remaining) == len(items):
                from app.errors import not_found
                raise not_found("KnowledgeItem", delete_code)
            items = remaining
        items.extend(additions or [])
        if not items:
            project.knowledge_pack_id = None
            project.knowledge_pack_version = None
            self.repo.flush()
            return self.knowledge_context(actor, project_id)
        version = self._next_pack_version(old_pack.version if old_pack else None) if bump_version else (old_pack.version if old_pack else "v1")
        pack = self.repo.add(
            KnowledgePack(
                tenant_id=actor.tenant_id,
                product_type_id=None,
                name=old_pack.name if old_pack else f"{project.name} Knowledge Pack",
                version=version,
                status="PROJECT_PRIVATE",
                content_hash=semantic_hash(items),
            )
        )
        self.repo.flush()
        self.repo.add_all([
            KnowledgeItem(
                tenant_id=actor.tenant_id,
                knowledge_pack_id=pack.id,
                item_type=str(item["item_type"]),
                code=str(item["code"]),
                title=str(item["title"]),
                content=str(item["content"]),
                parent_code=item.get("parent_code"),
                metadata_json=item.get("metadata", {}),
            )
            for item in items
        ])
        project.knowledge_pack_id = pack.id
        project.knowledge_pack_version = pack.version
        self.repo.flush()
        return self.knowledge_context(actor, project_id)

    @staticmethod
    def _next_pack_version(version: str | None) -> str:
        if not version:
            return "v1"
        match = re.fullmatch(r"([vV]?)(\d+)", version.strip())
        if match:
            return f"{match.group(1) or 'v'}{int(match.group(2)) + 1}"
        match = re.fullmatch(r"(\d+)\.0+", version.strip())
        if match:
            return f"{int(match.group(1)) + 1}.0"
        return f"{version}.1"

    def update_context(
        self, actor: Actor, project_id: str, data: ProjectContextUpdate
    ) -> ProjectContextRead:
        self._require_role(actor, project_id, {"OWNER", "EDITOR", "REVIEWER"})
        context = self.repo.project_context(actor, project_id)
        self._check_revision("ProjectContext", data.expected_revision, context.revision)
        changed = semantic_hash(context.constraints_json) != semantic_hash(data.items)
        context.constraints_json = data.items
        context.revision += 1
        if changed:
            for requirement in self.repo.list_requirements(actor, project_id):
                self._stale_requirement_downstream(actor.tenant_id, requirement.id)
        self.repo.flush()
        return ProjectContextRead(items=context.constraints_json, revision=context.revision)

    def list_requirements(self, actor: Actor, project_id: str) -> RequirementList:
        items = self.repo.list_requirements(actor, project_id)
        return RequirementList(items=[RequirementRead.model_validate(item) for item in items])

    def create_requirement(
        self, actor: Actor, project_id: str, data: RequirementCreate
    ) -> RequirementRead:
        self._require_role(actor, project_id, {"OWNER", "EDITOR", "REVIEWER"})
        digest = semantic_hash(data.title, data.original_text)
        requirement = self.repo.add(
            Requirement(
                tenant_id=actor.tenant_id,
                project_id=project_id,
                requirement_code=data.requirement_code,
                title=data.title,
                original_text=data.original_text,
                revision=1,
                semantic_hash=digest,
                created_by=actor.user_id,
            )
        )
        self.repo.flush()
        self.repo.add(
            RequirementRevision(
                tenant_id=actor.tenant_id,
                project_id=project_id,
                requirement_id=requirement.id,
                revision=1,
                title=requirement.title,
                original_text=requirement.original_text,
                semantic_hash=digest,
                change_summary="Initial revision.",
                created_by=actor.user_id,
            )
        )
        self.repo.flush()
        return RequirementRead.model_validate(requirement)

    def get_requirement(self, actor: Actor, requirement_id: str) -> RequirementRead:
        return RequirementRead.model_validate(self.repo.requirement(actor, requirement_id))

    def requirement_revisions(
        self, actor: Actor, requirement_id: str
    ) -> RequirementRevisionList:
        requirement = self.repo.requirement(actor, requirement_id)
        return RequirementRevisionList(
            items=[
                RequirementRevisionRead.model_validate(item)
                for item in self.repo.requirement_revisions(
                    actor.tenant_id, requirement.id
                )
            ]
        )

    def update_requirement(
        self, actor: Actor, requirement_id: str, data: RequirementUpdate
    ) -> RequirementRead:
        requirement = self.repo.requirement(actor, requirement_id)
        self._require_role(
            actor, requirement.project_id, {"OWNER", "EDITOR", "REVIEWER"}
        )
        self._check_revision("Requirement", data.expected_revision, requirement.revision)
        new_title = data.title if data.title is not None else requirement.title
        new_text = (
            data.original_text
            if data.original_text is not None
            else requirement.original_text
        )
        digest = semantic_hash(new_title, new_text)
        semantic_change = digest != requirement.semantic_hash
        requirement.revision += 1
        requirement.title = new_title
        requirement.original_text = new_text
        requirement.semantic_hash = digest
        self.repo.add(
            RequirementRevision(
                tenant_id=actor.tenant_id,
                project_id=requirement.project_id,
                requirement_id=requirement.id,
                revision=requirement.revision,
                title=new_title,
                original_text=new_text,
                semantic_hash=digest,
                change_summary=data.change_summary,
                created_by=actor.user_id,
            )
        )
        if semantic_change:
            self._stale_requirement_downstream(actor.tenant_id, requirement.id)
        self.repo.flush()
        return RequirementRead.model_validate(requirement)

    # Generation entry points: validate the human gate before creating a run.
    def start_analysis(
        self,
        actor: Actor,
        requirement_id: str,
        idempotency_key: str | None,
        data: AnalyzeRequest | None = None,
    ) -> RunRead:
        data = data or AnalyzeRequest()
        requirement = self.repo.requirement(actor, requirement_id)
        self._require_role(
            actor, requirement.project_id, {"OWNER", "EDITOR", "REVIEWER"}
        )
        self._validate_generation_scope(
            requirement, project_id=data.project_id, requirement_id=None
        )
        self._validate_generation_options(
            "ANALYSIS", data.options.model_dump(), data.user_instruction
        )
        if (
            data.requirement_revision is not None
            and data.requirement_revision != requirement.revision
        ):
            raise version_conflict(
                "Requirement", data.requirement_revision, requirement.revision
            )
        run, created = self._queue_run(
            actor,
            requirement,
            "ANALYSIS",
            idempotency_key,
            {
                "requirement_revision": requirement.revision,
                "options": data.options.model_dump(),
                "user_instruction": data.user_instruction,
            },
            request_identity={
                "project_id": data.project_id,
                "requirement_revision": data.requirement_revision,
                "options": data.options.model_dump(),
                "user_instruction": data.user_instruction,
            },
        )
        return self._dispatch(run, should_dispatch=created)

    def start_risks(
        self,
        actor: Actor,
        analysis_id: str,
        data: GenerateRequest,
        idempotency_key: str | None,
        *,
        project_id: str | None = None,
        requirement_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> RunRead:
        analysis = self.repo.analysis(actor, analysis_id)
        self._require_role(
            actor, analysis.project_id, {"OWNER", "EDITOR", "REVIEWER"}
        )
        if analysis.status != AssetStatus.APPROVED:
            raise gate_blocked(
                "Risk generation requires an APPROVED, non-stale analysis.",
                analysis_id=analysis.id,
                status=analysis.status,
            )
        requirement = self.repo.requirement(actor, analysis.requirement_id)
        self._validate_generation_scope(
            requirement, project_id=project_id, requirement_id=requirement_id
        )
        self._validate_generation_options("RISK", options or {})
        if analysis.source_requirement_revision != requirement.revision:
            raise gate_blocked(
                "Risk generation cannot use an analysis from an older requirement revision."
            )
        assertions = self.repo.assertions(actor.tenant_id, analysis.id)
        selected = self._select_ids(data, {item.id for item in assertions}, "assertion")
        selected_assertions = [item for item in assertions if item.id in set(selected)]
        run, created = self._queue_run(
            actor,
            requirement,
            "RISK",
            idempotency_key,
            {
                "source_id": analysis.id,
                "mode": data.mode,
                "selected_ids": selected,
                "options": options or {},
                "source_snapshot": {
                    "type": "ANALYSIS",
                    "id": analysis.id,
                    "asset_revision": analysis.asset_revision,
                    "status": analysis.status,
                    "source_requirement_revision": analysis.source_requirement_revision,
                    "semantic_hash": analysis.semantic_hash,
                    "summary": analysis.summary,
                    "ambiguities": analysis.ambiguities_json,
                    "why_generated": analysis.why_generated,
                    "assertions": [
                        {
                            "id": item.id,
                            "code": item.code,
                            "text": item.text,
                            "constraint": item.constraint_json,
                            "source_span": item.source_span,
                        }
                        for item in selected_assertions
                    ],
                },
            },
            request_identity={
                "source_id": analysis.id,
                "project_id": project_id,
                "requirement_id": requirement_id,
                "mode": data.mode,
                "selected_ids": data.selected_ids,
                "options": options or {},
            },
        )
        return self._dispatch(run, should_dispatch=created)

    def start_scenarios(
        self,
        actor: Actor,
        batch_id: str,
        data: GenerateRequest,
        idempotency_key: str | None,
        *,
        project_id: str | None = None,
        requirement_id: str | None = None,
        analysis_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> RunRead:
        batch = self.repo.risk_batch(actor, batch_id)
        self._require_role(
            actor, batch.project_id, {"OWNER", "EDITOR", "REVIEWER"}
        )
        if batch.status == AssetStatus.STALE:
            raise gate_blocked("Scenario generation cannot consume a STALE risk batch.")
        approved = [
            item
            for item in self.repo.risks(actor.tenant_id, batch.id)
            if item.status == AssetStatus.APPROVED
        ]
        if not approved:
            raise gate_blocked("Scenario generation requires at least one APPROVED risk.")
        selected = self._select_ids(data, {item.id for item in approved}, "risk")
        requirement = self.repo.requirement(actor, batch.requirement_id)
        self._validate_generation_scope(
            requirement, project_id=project_id, requirement_id=requirement_id
        )
        self._validate_generation_options("SCENARIO", options or {})
        if analysis_id is not None and analysis_id != batch.source_analysis_id:
            raise AppError(
                422,
                "SOURCE_ANALYSIS_MISMATCH",
                "analysis_id does not match the risk batch source analysis.",
            )
        selected_risks = [item for item in approved if item.id in set(selected)]
        assertion_codes = {
            item.id: item.code
            for item in self.repo.assertions(actor.tenant_id, batch.source_analysis_id)
        }
        run, created = self._queue_run(
            actor,
            requirement,
            "SCENARIO",
            idempotency_key,
            {
                "source_id": batch.id,
                "mode": data.mode,
                "selected_ids": selected,
                "options": options or {},
                "source_snapshot": {
                    "type": "RISK_BATCH",
                    "id": batch.id,
                    "revision": batch.revision,
                    "status": batch.status,
                    "source_analysis_id": batch.source_analysis_id,
                    "risks": [
                        {
                            "id": item.id,
                            "assertion_id": item.assertion_id,
                            "assertion_code": assertion_codes[item.assertion_id],
                            "code": item.code,
                            "title": item.title,
                            "description": item.description,
                            "likelihood": item.likelihood,
                            "impact": item.impact,
                            "rationale": item.rationale,
                            "requirement_gap": item.requirement_gap,
                            "why_generated": item.why_generated,
                            "status": item.status,
                            "asset_revision": item.asset_revision,
                            "semantic_hash": item.semantic_hash,
                            "knowledge_reference_codes": [
                                ref.reference_code
                                for ref in self.repo.references(
                                    actor.tenant_id, "RISK", item.id
                                )
                            ],
                        }
                        for item in selected_risks
                    ],
                },
            },
            request_identity={
                "source_id": batch.id,
                "project_id": project_id,
                "requirement_id": requirement_id,
                "analysis_id": analysis_id,
                "mode": data.mode,
                "selected_ids": data.selected_ids,
                "options": options or {},
            },
        )
        return self._dispatch(run, should_dispatch=created)

    def start_test_cases(
        self,
        actor: Actor,
        batch_id: str,
        data: GenerateRequest,
        idempotency_key: str | None,
        *,
        project_id: str | None = None,
        requirement_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> RunRead:
        batch = self.repo.scenario_batch(actor, batch_id)
        self._require_role(
            actor, batch.project_id, {"OWNER", "EDITOR", "REVIEWER"}
        )
        if batch.status == AssetStatus.STALE:
            raise gate_blocked("Test-case generation cannot consume a STALE scenario batch.")
        approved = [
            item
            for item in self.repo.scenarios(actor.tenant_id, batch.id)
            if item.status == AssetStatus.APPROVED
        ]
        if not approved:
            raise gate_blocked(
                "Test-case generation requires at least one APPROVED scenario."
            )
        selected = self._select_ids(data, {item.id for item in approved}, "scenario")
        requirement = self.repo.requirement(actor, batch.requirement_id)
        self._validate_generation_scope(
            requirement, project_id=project_id, requirement_id=requirement_id
        )
        self._validate_generation_options("TEST_CASE", options or {})
        selected_scenarios = [item for item in approved if item.id in set(selected)]
        source_risk_batch = self.repo.risk_batch_internal(
            actor.tenant_id, batch.source_risk_batch_id
        )
        risk_codes = {
            item.id: item.code
            for item in self.repo.risks(actor.tenant_id, source_risk_batch.id)
        }
        run, created = self._queue_run(
            actor,
            requirement,
            "TEST_CASE",
            idempotency_key,
            {
                "source_id": batch.id,
                "mode": data.mode,
                "selected_ids": selected,
                "options": options or {},
                "source_snapshot": {
                    "type": "SCENARIO_BATCH",
                    "id": batch.id,
                    "revision": batch.revision,
                    "status": batch.status,
                    "scenarios": [
                        {
                            "id": item.id,
                            "risk_id": item.risk_id,
                            "risk_code": risk_codes[item.risk_id],
                            "code": item.code,
                            "title": item.title,
                            "intent": item.intent,
                            "category": item.category,
                            "preconditions": item.preconditions_json,
                            "expected_result": item.expected_result,
                            "expected_result_status": item.expected_result_status,
                            "blocking_questions": item.blocking_questions_json,
                            "why_generated": item.why_generated,
                            "status": item.status,
                            "asset_revision": item.asset_revision,
                            "semantic_hash": item.semantic_hash,
                            "knowledge_reference_codes": [
                                ref.reference_code
                                for ref in self.repo.references(
                                    actor.tenant_id, "SCENARIO", item.id
                                )
                            ],
                        }
                        for item in selected_scenarios
                    ],
                },
            },
            request_identity={
                "source_id": batch.id,
                "project_id": project_id,
                "requirement_id": requirement_id,
                "mode": data.mode,
                "selected_ids": data.selected_ids,
                "options": options or {},
            },
        )
        return self._dispatch(run, should_dispatch=created)

    def process_run(
        self, tenant_id: str, run_id: str, *, retry_unexpected: bool = False
    ) -> RunRead:
        run = self.repo.ai_run_internal(tenant_id, run_id)
        self._execute_run(run, retry_unexpected=retry_unexpected)
        return RunRead.model_validate(run)

    def fail_run_after_retries(self, tenant_id: str, run_id: str) -> RunRead:
        run = self.repo.ai_run_internal(tenant_id, run_id)
        if run.status not in {RunStatus.SUCCEEDED, RunStatus.FAILED}:
            run.status = RunStatus.FAILED
            run.error_code = "AI_RUN_RETRIES_EXHAUSTED"
            run.error_message = "Transient AI processing failed after bounded retries."
            run.finished_at = utcnow()
            self.repo.flush()
        return RunRead.model_validate(run)

    def get_run(self, actor: Actor, run_id: str) -> RunRead:
        return RunRead.model_validate(self.repo.ai_run(actor, run_id))

    # Review and edit gates
    def review_analysis(
        self, actor: Actor, analysis_id: str, data: AnalysisReview
    ) -> AnalysisRead:
        analysis = self.repo.analysis(actor, analysis_id)
        self._require_role(actor, analysis.project_id, {"OWNER", "REVIEWER"})
        self._check_revision("Analysis", data.expected_revision, analysis.asset_revision)
        if analysis.status in {AssetStatus.STALE, AssetStatus.SUPERSEDED}:
            raise gate_blocked("A stale or superseded analysis cannot be reviewed.")
        was_approved = analysis.status == AssetStatus.APPROVED
        analysis.status = self._status_for_action(data.action)
        analysis.rejection_reason = data.rejection_reason if data.action == ReviewAction.REJECT else None
        analysis.rejection_note = data.rejection_note if data.action == ReviewAction.REJECT else None
        analysis.asset_revision += 1
        if was_approved and data.action == ReviewAction.REJECT:
            self._stale_analysis_downstream(actor.tenant_id, analysis.id)
        self.repo.flush()
        return self.get_analysis(actor, analysis.id)

    def update_analysis(self, actor: Actor, analysis_id: str, data: AnalysisUpdate) -> AnalysisRead:
        analysis = self.repo.analysis(actor, analysis_id)
        self._require_role(actor, analysis.project_id, {"OWNER", "EDITOR", "REVIEWER"})
        self._check_revision("Analysis", data.expected_revision, analysis.asset_revision)
        if analysis.status in {AssetStatus.STALE, AssetStatus.SUPERSEDED}:
            raise gate_blocked("A stale or superseded analysis cannot be edited.")
        before = analysis.semantic_hash
        if data.summary is not None:
            analysis.summary = data.summary
        if data.ambiguities is not None:
            analysis.ambiguities_json = data.ambiguities
        if data.why_generated is not None:
            analysis.why_generated = data.why_generated
        if data.assertions is not None:
            requirement = self.repo.requirement(actor, analysis.requirement_id)
            codes = [item.code for item in data.assertions]
            if len(codes) != len(set(codes)):
                raise AppError(422, "DUPLICATE_ASSERTION_CODE", "Assertion codes must be unique.")
            for item in data.assertions:
                if item.source_span not in requirement.original_text:
                    raise AppError(422, "INVALID_SOURCE_SPAN", "Assertion source_span must occur in the requirement text.")
            existing = {item.code: item for item in self.repo.assertions(actor.tenant_id, analysis.id)}
            incoming = {item.code: item for item in data.assertions}
            if self.repo.risk_batches(actor.tenant_id, analysis.requirement_id) and set(existing) - set(incoming):
                raise AppError(409, "ASSERTION_IN_USE", "Assertions already used by downstream risks cannot be removed; edit them or regenerate the analysis.")
            for code, current in existing.items():
                if code not in incoming:
                    self.repo.session.delete(current)
                    continue
                item = incoming[code]
                current.text = item.text
                current.constraint_json = item.constraint_json
                current.source_span = item.source_span
            for code, item in incoming.items():
                if code not in existing:
                    self.repo.add(RequirementAssertion(
                        tenant_id=actor.tenant_id, project_id=analysis.project_id,
                        requirement_id=analysis.requirement_id, analysis_id=analysis.id,
                        code=item.code, text=item.text, constraint_json=item.constraint_json,
                        source_span=item.source_span,
                    ))
            self.repo.flush()
        assertions = self.repo.assertions(actor.tenant_id, analysis.id)
        analysis.semantic_hash = semantic_hash(
            analysis.summary, analysis.ambiguities_json, analysis.why_generated,
            [{"code": item.code, "text": item.text, "constraint": item.constraint_json, "source_span": item.source_span} for item in assertions],
        )
        analysis.asset_revision += 1
        analysis.status = AssetStatus.HUMAN_EDITED
        analysis.rejection_reason = None
        analysis.rejection_note = None
        if analysis.semantic_hash != before:
            self._stale_analysis_downstream(actor.tenant_id, analysis.id)
        self.repo.flush()
        return self.get_analysis(actor, analysis.id)

    def get_analysis_for_requirement(
        self, actor: Actor, requirement_id: str, analysis_id: str
    ) -> AnalysisRead:
        requirement = self.repo.requirement(actor, requirement_id)
        analysis = self.repo.analysis(actor, analysis_id)
        if analysis.requirement_id != requirement.id:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Analysis is outside requirement scope.")
        return self.get_analysis(actor, analysis_id)

    def review_analysis_for_requirement(
        self,
        actor: Actor,
        requirement_id: str,
        analysis_id: str,
        data: AnalysisReview,
    ) -> AnalysisRead:
        self.get_analysis_for_requirement(actor, requirement_id, analysis_id)
        return self.review_analysis(actor, analysis_id, data)

    def update_risk(self, actor: Actor, risk_id: str, data: RiskUpdate) -> RiskRead:
        risk = self.repo.risk(actor, risk_id)
        self._require_role(actor, risk.project_id, {"OWNER", "EDITOR", "REVIEWER"})
        if risk.status in {AssetStatus.STALE, AssetStatus.SUPERSEDED}:
            raise gate_blocked("A stale or superseded risk cannot be edited.")
        self._check_revision("Risk", data.expected_revision, risk.asset_revision)
        before = risk.semantic_hash
        for field in ("title", "description", "likelihood", "impact", "rationale"):
            value = getattr(data, field)
            if value is not None:
                setattr(risk, field, value)
        risk.semantic_hash = risk_semantic_hash(risk)
        risk.asset_revision += 1
        risk.status = AssetStatus.HUMAN_EDITED
        risk.rejection_reason = None
        risk.rejection_note = None
        if risk.semantic_hash != before:
            self._stale_risk_downstream(actor.tenant_id, risk.id)
        batch = self.repo.risk_batch_internal(actor.tenant_id, risk.batch_id)
        self._update_batch_status(
            batch, self.repo.risks(actor.tenant_id, risk.batch_id)
        )
        self.repo.flush()
        return self._risk_read(actor.tenant_id, risk)

    def update_risk_in_batch(
        self, actor: Actor, batch_id: str, risk_id: str, data: RiskUpdate
    ) -> RiskRead:
        batch = self.repo.risk_batch(actor, batch_id)
        risk = self.repo.risk(actor, risk_id)
        if risk.batch_id != batch.id:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Risk is outside batch scope.")
        return self.update_risk(actor, risk_id, data)

    def update_scenario(
        self, actor: Actor, scenario_id: str, data: ScenarioUpdate
    ) -> ScenarioRead:
        scenario = self.repo.scenario(actor, scenario_id)
        self._require_role(
            actor, scenario.project_id, {"OWNER", "EDITOR", "REVIEWER"}
        )
        if scenario.status in {AssetStatus.STALE, AssetStatus.SUPERSEDED}:
            raise gate_blocked("A stale or superseded scenario cannot be edited.")
        self._check_revision("Scenario", data.expected_revision, scenario.asset_revision)
        before = scenario.semantic_hash
        for field in ("title", "intent", "category"):
            value = getattr(data, field)
            if value is not None:
                setattr(scenario, field, value)
        if data.preconditions is not None:
            scenario.preconditions_json = data.preconditions
        if "expected_result" in data.model_fields_set:
            scenario.expected_result = data.expected_result
        if data.expected_result_status is not None:
            scenario.expected_result_status = data.expected_result_status
        if data.blocking_questions is not None:
            scenario.blocking_questions_json = data.blocking_questions
        self._validate_expected(
            scenario.expected_result,
            scenario.expected_result_status,
            scenario.blocking_questions_json,
        )
        scenario.semantic_hash = scenario_semantic_hash(scenario)
        scenario.asset_revision += 1
        scenario.status = AssetStatus.HUMAN_EDITED
        scenario.rejection_reason = None
        scenario.rejection_note = None
        if scenario.semantic_hash != before:
            self._stale_scenario_downstream(actor.tenant_id, scenario.id)
        batch = self.repo.scenario_batch_internal(actor.tenant_id, scenario.batch_id)
        self._update_batch_status(
            batch, self.repo.scenarios(actor.tenant_id, scenario.batch_id)
        )
        self.repo.flush()
        return self._scenario_read(actor.tenant_id, scenario)

    def update_scenario_in_batch(
        self, actor: Actor, batch_id: str, scenario_id: str, data: ScenarioUpdate
    ) -> ScenarioRead:
        batch = self.repo.scenario_batch(actor, batch_id)
        scenario = self.repo.scenario(actor, scenario_id)
        if scenario.batch_id != batch.id:
            raise AppError(404, "RESOURCE_NOT_FOUND", "Scenario is outside batch scope.")
        return self.update_scenario(actor, scenario_id, data)

    def update_test_case(
        self, actor: Actor, test_case_id: str, data: TestCaseUpdate
    ) -> TestCaseRead:
        case = self.repo.test_case(actor, test_case_id)
        self._require_role(actor, case.project_id, {"OWNER", "EDITOR", "REVIEWER"})
        if case.status in {AssetStatus.STALE, AssetStatus.SUPERSEDED}:
            raise gate_blocked("A stale or superseded test case cannot be edited.")
        self._check_revision("TestCase", data.expected_revision, case.asset_revision)
        for field in ("title", "objective"):
            value = getattr(data, field)
            if value is not None:
                setattr(case, field, value)
        if data.preconditions is not None:
            case.preconditions_json = data.preconditions
        if data.configuration is not None:
            case.configuration_json = data.configuration
        if "expected_result" in data.model_fields_set:
            case.expected_result = data.expected_result
        if data.expected_result_status is not None:
            case.expected_result_status = data.expected_result_status
        if data.blocking_questions is not None:
            case.blocking_questions_json = data.blocking_questions
        if data.steps is not None:
            for step in self.repo.steps(actor.tenant_id, case.id):
                self.repo.session.delete(step)
            self.repo.flush()
            for sequence, step in enumerate(data.steps, start=1):
                self.repo.add(TestStep(
                    tenant_id=actor.tenant_id, project_id=case.project_id,
                    test_case_id=case.id, sequence=sequence, action=step.action,
                    expected_result=step.expected_result, test_data=step.test_data,
                ))
        self._validate_expected(
            case.expected_result,
            case.expected_result_status,
            case.blocking_questions_json,
        )
        case.semantic_hash = test_case_semantic_hash(case)
        case.asset_revision += 1
        case.status = AssetStatus.HUMAN_EDITED
        case.rejection_reason = None
        case.rejection_note = None
        batch = self.repo.test_case_batch_internal(actor.tenant_id, case.batch_id)
        self._update_batch_status(
            batch, self.repo.test_cases(actor.tenant_id, case.batch_id)
        )
        self.repo.flush()
        return self._test_case_read(actor.tenant_id, case)

    def delete_analysis(self, actor: Actor, analysis_id: str, data: AssetDelete) -> None:
        analysis = self.repo.analysis(actor, analysis_id)
        self._delete_asset(actor, analysis, data)
        self._stale_analysis_downstream(actor.tenant_id, analysis.id)
        self.repo.flush()

    def delete_risk(self, actor: Actor, risk_id: str, data: AssetDelete) -> None:
        risk = self.repo.risk(actor, risk_id)
        self._delete_asset(actor, risk, data)
        self._stale_risk_downstream(actor.tenant_id, risk.id)
        batch = self.repo.risk_batch_internal(actor.tenant_id, risk.batch_id)
        self._update_batch_status(batch, self.repo.risks(actor.tenant_id, risk.batch_id))
        self.repo.flush()

    def delete_scenario(self, actor: Actor, scenario_id: str, data: AssetDelete) -> None:
        scenario = self.repo.scenario(actor, scenario_id)
        self._delete_asset(actor, scenario, data)
        self._stale_scenario_downstream(actor.tenant_id, scenario.id)
        batch = self.repo.scenario_batch_internal(actor.tenant_id, scenario.batch_id)
        self._update_batch_status(batch, self.repo.scenarios(actor.tenant_id, scenario.batch_id))
        self.repo.flush()

    def delete_test_case(self, actor: Actor, test_case_id: str, data: AssetDelete) -> None:
        case = self.repo.test_case(actor, test_case_id)
        self._delete_asset(actor, case, data)
        batch = self.repo.test_case_batch_internal(actor.tenant_id, case.batch_id)
        self._update_batch_status(batch, self.repo.test_cases(actor.tenant_id, case.batch_id))
        self.repo.flush()

    def _delete_asset(self, actor: Actor, item: Any, data: AssetDelete) -> None:
        self._require_role(actor, item.project_id, {"OWNER", "EDITOR"})
        self._check_revision(item.__class__.__name__, data.expected_revision, item.asset_revision)
        item.deleted_at = utcnow()
        item.deleted_by = actor.user_id
        item.deletion_reason = data.reason
        item.asset_revision += 1

    def update_test_case_in_batch(
        self, actor: Actor, batch_id: str, case_id: str, data: TestCaseUpdate
    ) -> TestCaseRead:
        batch = self.repo.test_case_batch(actor, batch_id)
        case = self.repo.test_case(actor, case_id)
        if case.batch_id != batch.id:
            raise AppError(404, "RESOURCE_NOT_FOUND", "TestCase is outside batch scope.")
        return self.update_test_case(actor, case_id, data)

    def review_risk_batch(
        self, actor: Actor, batch_id: str, data: BatchReview
    ) -> RiskBatchRead:
        batch = self.repo.risk_batch(actor, batch_id)
        self._require_role(actor, batch.project_id, {"OWNER", "REVIEWER"})
        items = self.repo.risks(actor.tenant_id, batch.id)
        chosen = self._review_selection(items, data.risk_ids, data)
        invalidated = [item.id for item in chosen if item.status == AssetStatus.APPROVED]
        self._apply_review(chosen, data, "Risk")
        self._update_batch_status(batch, items)
        if data.action == ReviewAction.REJECT:
            for risk_id in invalidated:
                self._stale_risk_downstream(actor.tenant_id, risk_id)
        self.repo.flush()
        return self.get_risk_batch(actor, batch.id)

    def review_scenario_batch(
        self, actor: Actor, batch_id: str, data: BatchReview
    ) -> ScenarioBatchRead:
        batch = self.repo.scenario_batch(actor, batch_id)
        self._require_role(actor, batch.project_id, {"OWNER", "REVIEWER"})
        items = self.repo.scenarios(actor.tenant_id, batch.id)
        chosen = self._review_selection(items, data.scenario_ids, data)
        invalidated = [item.id for item in chosen if item.status == AssetStatus.APPROVED]
        # Scenario approval accepts the test intent (what/why), even when expected
        # behavior remains a visible clarification. The related case preserves the
        # null result and cannot itself be approved until clarified.
        self._apply_review(chosen, data, "Scenario")
        self._update_batch_status(batch, items)
        if data.action == ReviewAction.REJECT:
            for scenario_id in invalidated:
                self._stale_scenario_downstream(actor.tenant_id, scenario_id)
        self.repo.flush()
        return self.get_scenario_batch(actor, batch.id)

    def review_test_case_batch(
        self, actor: Actor, batch_id: str, data: BatchReview
    ) -> TestCaseBatchRead:
        batch = self.repo.test_case_batch(actor, batch_id)
        self._require_role(actor, batch.project_id, {"OWNER", "REVIEWER"})
        items = self.repo.test_cases(actor.tenant_id, batch.id)
        chosen = self._review_selection(items, data.test_case_ids, data)
        if data.action == ReviewAction.APPROVE:
            undefined = [
                item.id
                for item in chosen
                if item.expected_result_status
                == ExpectedResultStatus.CLARIFICATION_REQUIRED
            ]
            if undefined:
                raise gate_blocked(
                    "Test cases with undefined expected behavior cannot be approved.",
                    test_case_ids=undefined,
                )
            not_execution_ready = []
            for item in chosen:
                steps = self.repo.steps(actor.tenant_id, item.id)
                if (
                    not self._has_structured_content(item.configuration_json)
                    or not steps
                    or any(
                        not step.action.strip()
                        or not self._has_structured_content(step.test_data)
                        or step.expected_result is None
                        or not step.expected_result.strip()
                        for step in steps
                    )
                ):
                    not_execution_ready.append(item.id)
            if not_execution_ready:
                raise gate_blocked(
                    "Only execution-ready test cases can be approved.",
                    test_case_ids=not_execution_ready,
                )
        self._apply_review(chosen, data, "TestCase")
        self._update_batch_status(batch, items)
        self.repo.flush()
        return self.get_test_case_batch(actor, batch.id)

    # Rich reads for review screens
    def get_analysis(self, actor: Actor, analysis_id: str) -> AnalysisRead:
        analysis = self.repo.analysis(actor, analysis_id)
        assertions = [
            AssertionRead.model_validate(item)
            for item in self.repo.assertions(actor.tenant_id, analysis.id)
        ]
        refs = self._reference_reads(actor.tenant_id, "ANALYSIS", analysis.id)
        return AnalysisRead.model_validate(analysis).model_copy(
            update={"assertions": assertions, "knowledge_references": refs}
        )

    def get_risk_batch(self, actor: Actor, batch_id: str) -> RiskBatchRead:
        batch = self.repo.risk_batch(actor, batch_id)
        items = [
            self._risk_read(actor.tenant_id, item)
            for item in self.repo.risks(actor.tenant_id, batch.id)
        ]
        return RiskBatchRead.model_validate(batch).model_copy(update={"items": items})

    def get_scenario_batch(self, actor: Actor, batch_id: str) -> ScenarioBatchRead:
        batch = self.repo.scenario_batch(actor, batch_id)
        items = [
            self._scenario_read(actor.tenant_id, item)
            for item in self.repo.scenarios(actor.tenant_id, batch.id)
        ]
        return ScenarioBatchRead.model_validate(batch).model_copy(update={"items": items})

    def get_test_case_batch(self, actor: Actor, batch_id: str) -> TestCaseBatchRead:
        batch = self.repo.test_case_batch(actor, batch_id)
        items = [
            self._test_case_read(actor.tenant_id, item)
            for item in self.repo.test_cases(actor.tenant_id, batch.id)
        ]
        return TestCaseBatchRead.model_validate(batch).model_copy(update={"items": items})

    def workflow(self, actor: Actor, requirement_id: str) -> WorkflowRead:
        requirement = self.repo.requirement(actor, requirement_id)
        analyses = self.repo.analyses(actor.tenant_id, requirement.id)
        risk_batches = self.repo.risk_batches(actor.tenant_id, requirement.id)
        scenario_batches = self.repo.scenario_batches(actor.tenant_id, requirement.id)
        case_batches = self.repo.test_case_batches(actor.tenant_id, requirement.id)
        active = {
            "analysis": self._asset_summary(analyses[-1] if analyses else None),
            "risk_batch": self._batch_summary(
                risk_batches[-1] if risk_batches else None,
                self.repo.risks(actor.tenant_id, risk_batches[-1].id)
                if risk_batches
                else [],
            ),
            "scenario_batch": self._batch_summary(
                scenario_batches[-1] if scenario_batches else None,
                self.repo.scenarios(actor.tenant_id, scenario_batches[-1].id)
                if scenario_batches
                else [],
            ),
            "test_case_batch": self._batch_summary(
                case_batches[-1] if case_batches else None,
                self.repo.test_cases(actor.tenant_id, case_batches[-1].id)
                if case_batches
                else [],
            ),
        }
        runs = [
            RunRead.model_validate(item)
            for item in self.repo.ai_runs_for_requirement(
                actor.tenant_id, requirement.id
            )
        ]
        blockers: list[dict[str, Any]] = []
        if not analyses or analyses[-1].status != AssetStatus.APPROVED:
            blockers.append(
                {"code": "ANALYSIS_APPROVAL_REQUIRED", "message": "Approve analysis."}
            )
        if scenario_batches:
            for scenario in self.repo.scenarios(
                actor.tenant_id, scenario_batches[-1].id
            ):
                if (
                    scenario.expected_result_status
                    == ExpectedResultStatus.CLARIFICATION_REQUIRED
                ):
                    blockers.append(
                        {
                            "code": "UNDEFINED_EXPECTED_BEHAVIOR",
                            "message": (
                                "Expected behavior requires clarification before "
                                "the related test case can be approved."
                            ),
                            "asset_id": scenario.id,
                            "questions": scenario.blocking_questions_json,
                        }
                    )
        active_values = [value for value in active.values() if value is not None]
        if any(value["status"] == AssetStatus.STALE for value in active_values):
            current_stage = "STALE"
        elif any(run.status in {RunStatus.QUEUED, RunStatus.RUNNING} for run in runs):
            current_stage = "ANALYZING"
        elif case_batches:
            current_stage = (
                "READY"
                if case_batches[-1].status == AssetStatus.APPROVED
                else "TESTCASE_REVIEW"
            )
        elif scenario_batches:
            current_stage = (
                "TESTCASE_REVIEW"
                if scenario_batches[-1].status == AssetStatus.APPROVED
                else "SCENARIO_REVIEW"
            )
        elif risk_batches:
            current_stage = (
                "SCENARIO_REVIEW"
                if risk_batches[-1].status == AssetStatus.APPROVED
                else "RISK_REVIEW"
            )
        elif analyses:
            current_stage = (
                "RISK_REVIEW"
                if analyses[-1].status == AssetStatus.APPROVED
                else "ANALYSIS_REVIEW"
            )
        else:
            current_stage = "IMPORTED"

        stage_order = [
            "IMPORTED",
            "ANALYSIS_REVIEW",
            "RISK_REVIEW",
            "SCENARIO_REVIEW",
            "TESTCASE_REVIEW",
            "READY",
        ]
        current_index = (
            stage_order.index(current_stage) if current_stage in stage_order else -1
        )
        stages = [
            {
                "name": name,
                "status": (
                    "COMPLETE"
                    if current_index >= 0 and index < current_index
                    else "CURRENT"
                    if index == current_index
                    else "STALE"
                    if current_stage == "STALE" and active_values
                    else "PENDING"
                ),
            }
            for index, name in enumerate(stage_order)
        ]

        role = self.repo.membership(actor, requirement.project_id).role
        can_edit = role in {"OWNER", "EDITOR", "REVIEWER"}
        can_review = role in {"OWNER", "REVIEWER"}
        available_actions: list[str] = []
        if can_edit:
            available_actions.append("ANALYZE_REQUIREMENT")
            if analyses:
                available_actions.append("REGENERATE_ANALYSIS")
            analysis_gate_open = bool(
                analyses
                and analyses[-1].status == AssetStatus.APPROVED
                and analyses[-1].source_requirement_revision == requirement.revision
            )
            if analysis_gate_open:
                available_actions.append("GENERATE_RISKS")
                if risk_batches:
                    available_actions.append("REGENERATE_RISKS")
            risk_gate_open = bool(
                risk_batches
                and risk_batches[-1].status != AssetStatus.STALE
                and any(
                item.status == AssetStatus.APPROVED
                for item in self.repo.risks(actor.tenant_id, risk_batches[-1].id)
                )
            )
            if risk_gate_open:
                available_actions.append("GENERATE_SCENARIOS")
                if scenario_batches:
                    available_actions.append("REGENERATE_SCENARIOS")
            scenario_gate_open = bool(
                scenario_batches
                and scenario_batches[-1].status != AssetStatus.STALE
                and any(
                item.status == AssetStatus.APPROVED
                for item in self.repo.scenarios(
                    actor.tenant_id, scenario_batches[-1].id
                )
                )
            )
            if scenario_gate_open:
                available_actions.append("GENERATE_TEST_CASES")
                if case_batches:
                    available_actions.append("REGENERATE_TEST_CASES")
        if can_review:
            if analyses and analyses[-1].status in {
                AssetStatus.AI_DRAFT,
                AssetStatus.HUMAN_EDITED,
            }:
                available_actions.append("REVIEW_ANALYSIS")
            if risk_batches and any(
                item.status not in {AssetStatus.STALE, AssetStatus.SUPERSEDED}
                for item in self.repo.risks(
                    actor.tenant_id, risk_batches[-1].id
                )
            ):
                available_actions.append("REVIEW_RISKS")
            if scenario_batches and any(
                item.status not in {AssetStatus.STALE, AssetStatus.SUPERSEDED}
                for item in self.repo.scenarios(
                    actor.tenant_id, scenario_batches[-1].id
                )
            ):
                available_actions.append("REVIEW_SCENARIOS")
            if case_batches and any(
                item.status not in {AssetStatus.STALE, AssetStatus.SUPERSEDED}
                for item in self.repo.test_cases(
                    actor.tenant_id, case_batches[-1].id
                )
            ):
                available_actions.append("REVIEW_TEST_CASES")

        active_run_types = {
            run.run_type
            for run in runs
            if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
        }
        actions_by_run_type = {
            "ANALYSIS": {"ANALYZE_REQUIREMENT", "REGENERATE_ANALYSIS"},
            "RISK": {"GENERATE_RISKS", "REGENERATE_RISKS"},
            "SCENARIO": {"GENERATE_SCENARIOS", "REGENERATE_SCENARIOS"},
            "TEST_CASE": {"GENERATE_TEST_CASES", "REGENERATE_TEST_CASES"},
        }
        hidden_actions = {
            action
            for run_type in active_run_types
            for action in actions_by_run_type.get(run_type, set())
        }
        available_actions = [
            action for action in available_actions if action not in hidden_actions
        ]

        return WorkflowRead(
            requirement=RequirementRead.model_validate(requirement),
            current_stage=current_stage,
            stages=stages,
            active_assets=active,
            available_actions=available_actions,
            runs=runs,
            blockers=blockers,
        )

    def traceability(self, actor: Actor, project_id: str) -> TraceabilityRead:
        assets = self.repo.project_assets(actor, project_id)
        nodes: list[dict[str, Any]] = []
        for key, items in assets.items():
            node_type = key.removesuffix("s").upper()
            for item in items:
                nodes.append(
                    {
                        "type": node_type,
                        "id": item.id,
                        "code": getattr(
                            item,
                            "requirement_code",
                            getattr(item, "code", None),
                        ),
                        "title": getattr(
                            item, "title", getattr(item, "summary", None)
                        ),
                        "status": getattr(item, "status", None),
                    }
                )
        edges = [
            TraceabilityEdge.model_validate(item, from_attributes=True)
            for item in self.repo.project_relations(actor, project_id)
        ]
        return TraceabilityRead(nodes=nodes, edges=edges)

    def requirement_traceability(
        self, actor: Actor, requirement_id: str
    ) -> TraceabilityRead:
        requirement = self.repo.requirement(actor, requirement_id)
        graph = self.traceability(actor, requirement.project_id)
        connected = {requirement.id}
        changed = True
        while changed:
            changed = False
            for edge in graph.edges:
                if edge.from_id in connected and edge.to_id not in connected:
                    connected.add(edge.to_id)
                    changed = True
                if edge.to_id in connected and edge.from_id not in connected:
                    connected.add(edge.from_id)
                    changed = True
        return TraceabilityRead(
            nodes=[item for item in graph.nodes if item["id"] in connected],
            edges=[
                item
                for item in graph.edges
                if item.from_id in connected and item.to_id in connected
            ],
        )

    def coverage(self, actor: Actor, project_id: str) -> CoverageRead:
        assets = self.repo.project_assets(actor, project_id)
        requirements = assets["requirements"]
        analyses = [item for item in assets["analyses"] if item.status != "SUPERSEDED"]
        assertions = [
            item
            for item in assets["assertions"]
            if any(a.id == item.analysis_id and a.status != "STALE" for a in analyses)
        ]
        risks = [item for item in assets["risks"] if item.status != "SUPERSEDED"]
        scenarios = [
            item for item in assets["scenarios"] if item.status != "SUPERSEDED"
        ]
        cases = [item for item in assets["test_cases"] if item.status != "SUPERSEDED"]
        relations = self.repo.project_relations(actor, project_id)
        approved_risk_assertions = {
            item.assertion_id for item in risks if item.status == AssetStatus.APPROVED
        }
        approved_scenario_risks = {
            item.risk_id for item in scenarios if item.status == AssetStatus.APPROVED
        }
        analyzed_requirements = {
            item.requirement_id for item in analyses if item.status != AssetStatus.STALE
        }
        approved_requirements = {
            item.requirement_id for item in analyses if item.status == AssetStatus.APPROVED
        }
        stale_count = sum(
            1
            for collection in assets.values()
            for item in collection
            if getattr(item, "status", None) == AssetStatus.STALE
        )
        undefined_count = sum(
            1
            for item in [*scenarios, *cases]
            if getattr(item, "expected_result_status", None)
            == ExpectedResultStatus.CLARIFICATION_REQUIRED
        )
        requirement_gap_count = sum(
            1 for item in risks if item.requirement_gap and item.status != AssetStatus.STALE
        )
        covered_assertions = sum(
            1 for item in assertions if item.id in approved_risk_assertions
        )
        covered_risks = sum(1 for item in risks if item.id in approved_scenario_risks)
        return CoverageRead(
            requirements={
                "total": len(requirements),
                "analyzed": len(analyzed_requirements),
                "approved": len(approved_requirements),
            },
            assertions=self._ratio(covered_assertions, len(assertions)),
            risks=self._ratio(covered_risks, len(risks)),
            scenarios={
                "total": len(scenarios),
                "approved": sum(
                    1 for item in scenarios if item.status == AssetStatus.APPROVED
                ),
            },
            cases={
                "total": len(cases),
                "approved": sum(
                    1 for item in cases if item.status == AssetStatus.APPROVED
                ),
            },
            issues={
                "requirement_gaps": requirement_gap_count,
                "undefined_expected_behaviors": undefined_count,
                "stale_assets": stale_count,
            },
        )

    # Internal pipeline: ContextBuilder -> Retriever -> Agent -> validators -> persist.
    def _execute_run(
        self, run: AIRun, *, retry_unexpected: bool = False
    ) -> None:
        started_at = utcnow()
        if not self.repo.claim_ai_run(run.tenant_id, run.id, started_at):
            return
        run.status = RunStatus.RUNNING
        run.started_at = started_at
        self.repo.flush()
        try:
            with self.repo.begin_nested():
                self._validate_executor_snapshot(run)
                if run.run_type == "ANALYSIS":
                    result_type, result_id = "ANALYSIS", self._generate_analysis(run)
                elif run.run_type == "RISK":
                    result_type, result_id = "RISK_BATCH", self._generate_risks(run)
                elif run.run_type == "SCENARIO":
                    result_type, result_id = "SCENARIO_BATCH", self._generate_scenarios(run)
                elif run.run_type == "TEST_CASE":
                    result_type, result_id = "TEST_CASE_BATCH", self._generate_test_cases(run)
                else:
                    raise AppError(
                        422, "UNKNOWN_RUN_TYPE", f"Unknown run type {run.run_type}."
                    )
            run.status = RunStatus.SUCCEEDED
            run.result_type = result_type
            run.result_id = result_id
            run.output_json = {"result_type": result_type, "result_id": result_id}
        except AppError as exc:
            run.status = RunStatus.FAILED
            run.error_code = exc.code
            run.error_message = exc.message
        except Exception:  # worker must leave an inspectable terminal run
            if retry_unexpected:
                raise
            run.status = RunStatus.FAILED
            run.error_code = "AI_RUN_FAILED"
            run.error_message = "AI processing failed unexpectedly."
        run.finished_at = utcnow()
        self.repo.flush()

    def _generate_analysis(self, run: AIRun) -> str:
        snapshot = self._snapshot(run)
        requirement_input = snapshot["requirement"]
        requirement = self.repo.requirement_internal(run.tenant_id, run.requirement_id)
        project = self.repo.project_internal(run.tenant_id, run.project_id)
        draft = self.gateway.analyze(
            requirement_input["original_text"], self._snapshot_knowledge(run)
        )
        DomainValidator.analysis(draft, requirement_input["original_text"])
        stale = self._snapshot_inputs_changed(run)
        prior = self.repo.analyses(run.tenant_id, requirement.id)
        if not stale:
            for item in prior:
                if item.status not in {AssetStatus.SUPERSEDED, AssetStatus.STALE}:
                    item.status = AssetStatus.SUPERSEDED
                    self._stale_analysis_downstream(run.tenant_id, item.id)
        revision = max((item.asset_revision for item in prior), default=0) + 1
        analysis = self.repo.add(
            Analysis(
                tenant_id=run.tenant_id,
                project_id=project.id,
                requirement_id=requirement.id,
                source_requirement_revision=requirement_input["revision"],
                asset_revision=revision,
                status=AssetStatus.STALE if stale else AssetStatus.AI_DRAFT,
                summary=draft.summary,
                ambiguities_json=draft.ambiguities,
                semantic_hash=semantic_hash(draft.model_dump()),
                why_generated=draft.why_generated,
                supersedes_id=prior[-1].id if prior else None,
            )
        )
        self.repo.flush()
        for assertion_draft in draft.assertions:
            assertion = self.repo.add(
                RequirementAssertion(
                    tenant_id=run.tenant_id,
                    project_id=project.id,
                    requirement_id=requirement.id,
                    analysis_id=analysis.id,
                    code=assertion_draft.code,
                    text=assertion_draft.text,
                    constraint_json=assertion_draft.constraint.model_dump(),
                    source_span=assertion_draft.source_span,
                )
            )
            self.repo.flush()
            self._relation(
                run.tenant_id,
                project.id,
                "REQUIREMENT",
                requirement.id,
                "CONTAINS",
                "ASSERTION",
                assertion.id,
            )
        self._add_references(run, project.id, "ANALYSIS", analysis.id, draft.knowledge_reference_codes)
        return analysis.id

    def _generate_risks(self, run: AIRun) -> str:
        source = self._snapshot(run)["source"]
        self.repo.analysis_internal(run.tenant_id, source["id"])
        project = self.repo.project_internal(run.tenant_id, run.project_id)
        selected_assertions = source["assertions"]
        analysis_draft = AnalysisDraft(
            summary=source["summary"],
            assertions=[
                AssertionDraft(
                    code=item["code"],
                    text=item["text"],
                    constraint=item["constraint"],
                    source_span=item["source_span"],
                )
                for item in selected_assertions
            ],
            ambiguities=source["ambiguities"],
            why_generated=source["why_generated"],
        )
        drafts = self.gateway.generate_risks(
            analysis_draft, self._snapshot_knowledge(run)
        )
        DomainValidator.risks(drafts, {item["code"] for item in selected_assertions})
        stale = self._snapshot_inputs_changed(run)
        prior = self.repo.risk_batches(run.tenant_id, run.requirement_id)
        if not stale:
            for prior_batch in prior:
                for prior_risk in self.repo.risks(run.tenant_id, prior_batch.id):
                    self._stale_risk_downstream(run.tenant_id, prior_risk.id)
            self._supersede_batches(prior, self.repo.risks, run.tenant_id)
        batch = self.repo.add(
            RiskBatch(
                tenant_id=run.tenant_id,
                project_id=project.id,
                requirement_id=run.requirement_id,
                source_analysis_id=source["id"],
                revision=max((item.revision for item in prior), default=0) + 1,
                status=AssetStatus.STALE if stale else AssetStatus.AI_DRAFT,
                generation_mode=self._snapshot_command(run).get("mode", GenerationMode.ALL),
                supersedes_id=prior[-1].id if prior else None,
            )
        )
        self.repo.flush()
        assertions_by_code = {item["code"]: item for item in selected_assertions}
        for draft in drafts:
            source = assertions_by_code[draft.assertion_code]
            risk = self.repo.add(
                Risk(
                    tenant_id=run.tenant_id,
                    project_id=project.id,
                    batch_id=batch.id,
                    assertion_id=source["id"],
                    code=draft.code,
                    title=draft.title,
                    description=draft.description,
                    likelihood=draft.likelihood,
                    impact=draft.impact,
                    rationale=draft.rationale,
                    requirement_gap=draft.requirement_gap,
                    why_generated=draft.why_generated,
                    status=AssetStatus.STALE if stale else AssetStatus.AI_DRAFT,
                    semantic_hash=risk_semantic_hash(draft),
                )
            )
            self.repo.flush()
            self._relation(
                run.tenant_id,
                project.id,
                "RISK",
                risk.id,
                "DERIVED_FROM",
                "ASSERTION",
                source["id"],
            )
            self._add_references(run, project.id, "RISK", risk.id, draft.knowledge_reference_codes)
        return batch.id

    def _generate_scenarios(self, run: AIRun) -> str:
        source_snapshot = self._snapshot(run)["source"]
        source_batch = self.repo.risk_batch_internal(
            run.tenant_id, source_snapshot["id"]
        )
        project = self.repo.project_internal(run.tenant_id, run.project_id)
        risks = source_snapshot["risks"]
        risk_drafts = [
            RiskDraft(
                code=item["code"],
                assertion_code=item["assertion_code"],
                title=item["title"],
                description=item["description"],
                likelihood=item["likelihood"],
                impact=item["impact"],
                rationale=item["rationale"],
                requirement_gap=item["requirement_gap"],
                why_generated=item["why_generated"],
                knowledge_reference_codes=item["knowledge_reference_codes"],
            )
            for item in risks
        ]
        drafts = self.gateway.generate_scenarios(
            risk_drafts, self._snapshot_knowledge(run)
        )
        DomainValidator.scenarios(drafts, {item.code for item in risk_drafts})
        stale = self._snapshot_inputs_changed(run)
        prior = self.repo.scenario_batches(run.tenant_id, run.requirement_id)
        if not stale:
            for prior_batch in prior:
                for prior_scenario in self.repo.scenarios(
                    run.tenant_id, prior_batch.id
                ):
                    self._stale_scenario_downstream(
                        run.tenant_id, prior_scenario.id
                    )
            self._supersede_batches(prior, self.repo.scenarios, run.tenant_id)
        batch = self.repo.add(
            ScenarioBatch(
                tenant_id=run.tenant_id,
                project_id=project.id,
                requirement_id=run.requirement_id,
                source_risk_batch_id=source_snapshot["id"],
                revision=max((item.revision for item in prior), default=0) + 1,
                status=AssetStatus.STALE if stale else AssetStatus.AI_DRAFT,
                generation_mode=self._snapshot_command(run).get("mode", GenerationMode.ALL),
                supersedes_id=prior[-1].id if prior else None,
            )
        )
        self.repo.flush()
        risks_by_code = {item["code"]: item for item in risks}
        for draft in drafts:
            source = risks_by_code[draft.risk_code]
            scenario = self.repo.add(
                Scenario(
                    tenant_id=run.tenant_id,
                    project_id=project.id,
                    batch_id=batch.id,
                    risk_id=source["id"],
                    code=draft.code,
                    title=draft.title,
                    intent=draft.intent,
                    category=draft.category,
                    preconditions_json=draft.preconditions,
                    expected_result=draft.expected_result,
                    expected_result_status=draft.expected_result_status,
                    blocking_questions_json=draft.blocking_questions,
                    why_generated=draft.why_generated,
                    status=AssetStatus.STALE if stale else AssetStatus.AI_DRAFT,
                    semantic_hash=scenario_semantic_hash(draft),
                )
            )
            self.repo.flush()
            self._relation(
                run.tenant_id,
                project.id,
                "SCENARIO",
                scenario.id,
                "VALIDATES",
                "RISK",
                source["id"],
            )
            self._add_references(run, project.id, "SCENARIO", scenario.id, draft.knowledge_reference_codes)
        return batch.id

    def _generate_test_cases(self, run: AIRun) -> str:
        source_snapshot = self._snapshot(run)["source"]
        source_batch = self.repo.scenario_batch_internal(
            run.tenant_id, source_snapshot["id"]
        )
        project = self.repo.project_internal(run.tenant_id, run.project_id)
        scenarios = source_snapshot["scenarios"]
        drafts_in = [
            ScenarioDraft(
                code=item["code"],
                risk_code=item["risk_code"],
                title=item["title"],
                intent=item["intent"],
                category=item["category"],
                preconditions=item["preconditions"],
                expected_result=item["expected_result"],
                expected_result_status=item["expected_result_status"],
                blocking_questions=item["blocking_questions"],
                why_generated=item["why_generated"],
                knowledge_reference_codes=item["knowledge_reference_codes"],
            )
            for item in scenarios
        ]
        drafts = self.gateway.generate_test_cases(
            drafts_in, self._snapshot_knowledge(run)
        )
        DomainValidator.test_cases(drafts, {item.code for item in drafts_in})
        stale = self._snapshot_inputs_changed(run)
        prior = self.repo.test_case_batches(run.tenant_id, run.requirement_id)
        if not stale:
            self._supersede_batches(prior, self.repo.test_cases, run.tenant_id)
        batch = self.repo.add(
            TestCaseBatch(
                tenant_id=run.tenant_id,
                project_id=project.id,
                requirement_id=run.requirement_id,
                source_scenario_batch_id=source_snapshot["id"],
                revision=max((item.revision for item in prior), default=0) + 1,
                status=AssetStatus.STALE if stale else AssetStatus.AI_DRAFT,
                generation_mode=self._snapshot_command(run).get("mode", GenerationMode.ALL),
                supersedes_id=prior[-1].id if prior else None,
            )
        )
        self.repo.flush()
        scenarios_by_code = {item["code"]: item for item in scenarios}
        for draft in drafts:
            source = scenarios_by_code[draft.scenario_code]
            case = self.repo.add(
                TestCase(
                    tenant_id=run.tenant_id,
                    project_id=project.id,
                    batch_id=batch.id,
                    scenario_id=source["id"],
                    code=draft.code,
                    title=draft.title,
                    objective=draft.objective,
                    preconditions_json=draft.preconditions,
                    configuration_json=draft.configuration,
                    expected_result=draft.expected_result,
                    expected_result_status=draft.expected_result_status,
                    blocking_questions_json=draft.blocking_questions,
                    why_generated=draft.why_generated,
                    status=AssetStatus.STALE if stale else AssetStatus.AI_DRAFT,
                    semantic_hash=test_case_semantic_hash(draft),
                )
            )
            self.repo.flush()
            self.repo.add_all(
                [
                    TestStep(
                        tenant_id=run.tenant_id,
                        project_id=project.id,
                        test_case_id=case.id,
                        sequence=step.sequence,
                        action=step.action,
                        expected_result=step.expected_result,
                        test_data=step.test_data,
                    )
                    for step in draft.steps
                ]
            )
            self._relation(
                run.tenant_id,
                project.id,
                "TEST_CASE",
                case.id,
                "IMPLEMENTS",
                "SCENARIO",
                source["id"],
            )
            self._add_references(run, project.id, "TEST_CASE", case.id, draft.knowledge_reference_codes)
        return batch.id

    # Small helpers
    def _queue_run(
        self,
        actor: Actor,
        requirement: Requirement,
        run_type: str,
        idempotency_key: str | None,
        input_json: dict[str, Any],
        *,
        request_identity: dict[str, Any] | None = None,
    ) -> tuple[AIRun, bool]:
        key = idempotency_key or str(uuid4())
        command = dict(input_json)
        source_snapshot = command.pop("source_snapshot", None)
        identity = request_identity if request_identity is not None else command
        request_hash = semantic_hash(requirement.id, run_type, identity)
        # PostgreSQL row locking makes the following replay/active-run checks and
        # insert one admission critical section. SQLite ignores FOR UPDATE but is
        # used only for deterministic local/test execution in this slice.
        self.repo.lock_requirement_for_run(actor.tenant_id, requirement.id)
        existing = self.repo.ai_run_by_key(
            actor.tenant_id, requirement.project_id, actor.user_id, run_type, key
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise AppError(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was already used with a different request.",
                )
            return existing, False
        active = self.repo.active_ai_run(
            actor.tenant_id, requirement.id, run_type
        )
        if active is not None:
            raise AppError(
                409,
                "AI_RUN_ALREADY_ACTIVE",
                "Another AI run of this type is already active for the requirement.",
                {"run_id": active.id, "run_type": run_type},
            )

        project = self.repo.project_internal(actor.tenant_id, requirement.project_id)
        context = self.repo.project_context(actor, requirement.project_id)
        knowledge_items = [
            {
                "id": item.id,
                "item_type": item.item_type,
                "code": item.code,
                "title": item.title,
                "content": item.content,
                "parent_code": item.parent_code,
                "metadata": item.metadata_json,
            }
            for item in (
                self.repo.knowledge_items(actor.tenant_id, project.knowledge_pack_id)
                if project.knowledge_pack_id
                else []
            )
        ]
        snapshot: dict[str, Any] = {
            "format_version": 1,
            "requirement": {
                "id": requirement.id,
                "revision": requirement.revision,
                "title": requirement.title,
                "original_text": requirement.original_text,
                "semantic_hash": requirement.semantic_hash,
            },
            # Flat fields remain for current API clients while the structured
            # values below are the immutable worker inputs.
            "requirement_revision": requirement.revision,
            "knowledge_pack_id": project.knowledge_pack_id,
            "knowledge_pack_version": project.knowledge_pack_version,
            "project_context_revision": context.revision,
            "project_context": {
                "revision": context.revision,
                "summary": context.summary,
                "items": context.constraints_json,
            },
            "project_context_hash": semantic_hash(
                context.summary, context.constraints_json
            ),
            "knowledge_items": knowledge_items,
            "knowledge_content_hash": semantic_hash(knowledge_items),
            "command": command,
            "provider": self.settings.llm_provider,
            "model": self.settings.llm_model,
            "prompt_version": self.settings.prompt_version,
            "validator_version": self.settings.validator_version,
            "policy_version": self.settings.policy_version,
        }
        if source_snapshot is not None:
            snapshot["source"] = source_snapshot
        normalized_input = json.loads(
            json.dumps(
                {
                    **command,
                    "input_snapshot": snapshot,
                },
                default=str,
            )
        )
        try:
            with self.repo.begin_nested():
                run = self.repo.add(
                    AIRun(
                        tenant_id=actor.tenant_id,
                        project_id=requirement.project_id,
                        requirement_id=requirement.id,
                        actor_id=actor.user_id,
                        run_type=run_type,
                        status=RunStatus.QUEUED,
                        model=self.settings.llm_model,
                        idempotency_key=key,
                        request_hash=request_hash,
                        input_json=normalized_input,
                    )
                )
                self.repo.flush()
            return run, True
        except IntegrityError:
            # Another request may have inserted the same actor-scoped key between
            # our lookup and insert. The savepoint keeps the outer request usable.
            existing = self.repo.ai_run_by_key(
                actor.tenant_id,
                requirement.project_id,
                actor.user_id,
                run_type,
                key,
            )
            if existing is None:
                raise
            if existing.request_hash != request_hash:
                raise AppError(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was already used with a different request.",
                )
            return existing, False

    def _dispatch(self, run: AIRun, *, should_dispatch: bool = True) -> RunRead:
        if not should_dispatch or run.status != RunStatus.QUEUED:
            return RunRead.model_validate(run)
        if self.settings.ai_task_mode == "inline":
            self._execute_run(run)
        else:
            self.repo.commit()
            from app.ai.tasks import process_ai_run

            process_ai_run.delay(run.tenant_id, run.id)
        return RunRead.model_validate(run)

    @staticmethod
    def _select_ids(data: GenerateRequest, allowed: set[str], label: str) -> list[str]:
        if data.mode == GenerationMode.SELECTED and not data.selected_ids:
            raise AppError(
                422,
                "SELECTION_REQUIRED",
                f"SELECTED mode requires at least one {label} id.",
            )
        selected = data.selected_ids or sorted(allowed)
        invalid = set(selected) - allowed
        if invalid:
            raise AppError(
                422,
                "INVALID_SELECTION",
                f"Selected {label}s are not eligible in this source batch.",
                {"ids": sorted(invalid)},
            )
        return selected

    @staticmethod
    def _validate_generation_scope(
        requirement: Requirement,
        *,
        project_id: str | None,
        requirement_id: str | None,
    ) -> None:
        if project_id is not None and project_id != requirement.project_id:
            raise AppError(
                422,
                "PROJECT_SCOPE_MISMATCH",
                "project_id does not match the selected source asset.",
            )
        if requirement_id is not None and requirement_id != requirement.id:
            raise AppError(
                422,
                "REQUIREMENT_SCOPE_MISMATCH",
                "requirement_id does not match the selected source asset.",
            )

    @staticmethod
    def _validate_generation_options(
        run_type: str,
        options: dict[str, Any],
        user_instruction: str | None = None,
    ) -> None:
        supported_profiles: dict[str, dict[str, Any]] = {
            "ANALYSIS": {
                "strict_grounding": True,
                "include_questions": True,
                "include_dependency_analysis": True,
                "include_testability_analysis": True,
                "language": "zh-CN",
            },
            "RISK": {
                "include_product_risks": True,
                "include_failure_modes": True,
                "include_dependency_risks": True,
                "include_requirement_gaps": True,
                "minimum_priority": "LOW",
            },
            "SCENARIO": {
                "include_nominal": True,
                "include_boundary": True,
                "include_negative": True,
                "include_fault": True,
                "include_recovery": True,
                "include_persistence": True,
                "include_interaction": True,
                "include_regression": True,
            },
            "TEST_CASE": {
                "generation_strategy": "ONE_OR_MORE_PER_SCENARIO",
                "step_granularity": "EXECUTION_READY",
                "include_preconditions": True,
                "include_configuration": True,
                "include_test_data": True,
                "expected_result_per_step": True,
                "avoid_unspecified_behavior": True,
            },
        }
        supported = supported_profiles[run_type]
        unsupported = [
            key
            for key, value in options.items()
            if key not in supported or value != supported[key]
        ]
        if user_instruction is not None and user_instruction.strip():
            unsupported.append("user_instruction")
        if unsupported:
            raise AppError(
                422,
                "GENERATION_OPTION_UNSUPPORTED",
                "The deterministic P0 provider cannot honor the requested generation options.",
                {
                    "run_type": run_type,
                    "fields": sorted(set(unsupported)),
                    "supported_profile": supported,
                },
            )

    def _require_role(
        self, actor: Actor, project_id: str, allowed_roles: set[str]
    ) -> None:
        membership = self.repo.membership(actor, project_id)
        if membership.role not in allowed_roles:
            raise AppError(
                403,
                "PROJECT_ROLE_REQUIRED",
                "The current project role cannot perform this action.",
                {
                    "actual_role": membership.role,
                    "allowed_roles": sorted(allowed_roles),
                },
            )

    @staticmethod
    def _check_revision(resource: str, expected: int, actual: int) -> None:
        if expected != actual:
            raise version_conflict(resource, expected, actual)

    @staticmethod
    def _status_for_action(action: ReviewAction) -> AssetStatus:
        return (
            AssetStatus.APPROVED
            if action == ReviewAction.APPROVE
            else AssetStatus.REJECTED
        )

    def _review_selection(
        self, items: list[Any], ids: list[str], data: BatchReview
    ) -> list[Any]:
        chosen = items if not ids else [item for item in items if item.id in set(ids)]
        if not chosen or (ids and len(chosen) != len(set(ids))):
            raise AppError(422, "INVALID_SELECTION", "Review selection is invalid.")
        for item in chosen:
            if item.id not in data.expected_revisions:
                raise AppError(
                    422,
                    "EXPECTED_REVISION_REQUIRED",
                    "Every reviewed item requires an expected revision.",
                    {"id": item.id},
                )
            self._check_revision(
                item.__class__.__name__,
                data.expected_revisions[item.id],
                item.asset_revision,
            )
            if item.status in {AssetStatus.STALE, AssetStatus.SUPERSEDED}:
                raise gate_blocked("Stale or superseded assets cannot be reviewed.", id=item.id)
        return chosen

    def _apply_review(
        self, chosen: list[Any], data: BatchReview, resource: str
    ) -> None:
        status = self._status_for_action(data.action)
        for item in chosen:
            item.status = status
            item.rejection_reason = data.rejection_reason if data.action == ReviewAction.REJECT else None
            item.rejection_note = data.rejection_note if data.action == ReviewAction.REJECT else None
            item.asset_revision += 1

    @staticmethod
    def _update_batch_status(batch: Any, items: list[Any]) -> None:
        if not items:
            batch.status = AssetStatus.HUMAN_EDITED
            return
        statuses = {item.status for item in items}
        if statuses == {AssetStatus.APPROVED}:
            batch.status = AssetStatus.APPROVED
        elif statuses == {AssetStatus.REJECTED}:
            batch.status = AssetStatus.REJECTED
        else:
            batch.status = AssetStatus.HUMAN_EDITED

    @staticmethod
    def _validate_expected(
        result: str | None, status: str, questions: list[str]
    ) -> None:
        if status == ExpectedResultStatus.DEFINED and (
            not result or not result.strip() or questions
        ):
            raise AppError(
                422,
                "EXPECTED_RESULT_INVALID",
                "DEFINED requires a result and no blocking questions.",
            )
        if status == ExpectedResultStatus.CLARIFICATION_REQUIRED and (
            result is not None or not questions
        ):
            raise AppError(
                422,
                "EXPECTED_RESULT_INVALID",
                "CLARIFICATION_REQUIRED requires null result and blocking questions.",
            )

    @staticmethod
    def _has_structured_content(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (bool, int, float)):
            return True
        if isinstance(value, list):
            return bool(value) and any(
                WorkflowService._has_structured_content(item) for item in value
            )
        if isinstance(value, dict):
            return bool(value) and any(
                WorkflowService._has_structured_content(item)
                for item in value.values()
            )
        return False

    def _stale_requirement_downstream(self, tenant_id: str, requirement_id: str) -> None:
        for item in self.repo.analyses(tenant_id, requirement_id):
            self._mark_stale(item)
        for batch in self.repo.risk_batches(tenant_id, requirement_id):
            self._mark_stale(batch)
            for item in self.repo.risks(tenant_id, batch.id):
                self._mark_stale(item)
        for batch in self.repo.scenario_batches(tenant_id, requirement_id):
            self._mark_stale(batch)
            for item in self.repo.scenarios(tenant_id, batch.id):
                self._mark_stale(item)
        for batch in self.repo.test_case_batches(tenant_id, requirement_id):
            self._mark_stale(batch)
            for item in self.repo.test_cases(tenant_id, batch.id):
                self._mark_stale(item)

    def _stale_analysis_downstream(self, tenant_id: str, analysis_id: str) -> None:
        analysis = self.repo.analysis_internal(tenant_id, analysis_id)
        for batch in self.repo.risk_batches(tenant_id, analysis.requirement_id):
            if batch.source_analysis_id != analysis_id:
                continue
            self._mark_stale(batch)
            for risk in self.repo.risks(tenant_id, batch.id):
                self._mark_stale(risk)
                self._stale_risk_downstream(tenant_id, risk.id)

    def _stale_risk_downstream(self, tenant_id: str, risk_id: str) -> None:
        for scenario in self.repo.scenarios_for_risk(tenant_id, risk_id):
            self._mark_stale(scenario)
            batch = self.repo.scenario_batch_internal(tenant_id, scenario.batch_id)
            self._mark_stale(batch)
            self._stale_scenario_downstream(tenant_id, scenario.id)

    def _stale_scenario_downstream(self, tenant_id: str, scenario_id: str) -> None:
        for case in self.repo.test_cases_for_scenario(tenant_id, scenario_id):
            self._mark_stale(case)
            batch = self.repo.test_case_batch_internal(tenant_id, case.batch_id)
            self._mark_stale(batch)

    @staticmethod
    def _mark_stale(item: Any) -> None:
        if item.status != AssetStatus.SUPERSEDED:
            item.status = AssetStatus.STALE

    @staticmethod
    def _supersede_batches(
        batches: list[Any], item_loader: Any, tenant_id: str
    ) -> None:
        for batch in batches:
            if batch.status != AssetStatus.STALE:
                batch.status = AssetStatus.SUPERSEDED
            for item in item_loader(tenant_id, batch.id):
                if item.status != AssetStatus.STALE:
                    item.status = AssetStatus.SUPERSEDED

    @staticmethod
    def _snapshot(run: AIRun) -> dict[str, Any]:
        snapshot = run.input_json.get("input_snapshot")
        if not isinstance(snapshot, dict) or snapshot.get("format_version") != 1:
            raise AppError(
                422,
                "AI_RUN_SNAPSHOT_INVALID",
                "AI run is missing the immutable version-1 input snapshot.",
            )
        return snapshot

    def _validate_executor_snapshot(self, run: AIRun) -> None:
        snapshot = self._snapshot(run)
        expected = {
            "provider": self.settings.llm_provider,
            "model": self.settings.llm_model,
            "prompt_version": self.settings.prompt_version,
            "validator_version": self.settings.validator_version,
            "policy_version": self.settings.policy_version,
        }
        mismatches = {
            key: {"queued": snapshot.get(key), "worker": current}
            for key, current in expected.items()
            if snapshot.get(key) != current
        }
        if run.model != snapshot.get("model"):
            mismatches["run_model"] = {
                "queued": snapshot.get("model"),
                "worker": run.model,
            }
        if mismatches:
            raise AppError(
                409,
                "AI_RUN_EXECUTOR_VERSION_MISMATCH",
                "The queued run requires an unavailable executor version; submit a new run.",
                mismatches,
            )

    def _snapshot_command(self, run: AIRun) -> dict[str, Any]:
        command = self._snapshot(run).get("command")
        if not isinstance(command, dict):
            raise AppError(
                422,
                "AI_RUN_SNAPSHOT_INVALID",
                "AI run snapshot is missing its command payload.",
            )
        return command

    def _snapshot_knowledge(self, run: AIRun) -> dict[str, str]:
        grounding = {
            item["code"]: item["content"]
            for item in self._snapshot(run).get("knowledge_items", [])
        }
        grounding["__PROJECT_CONTEXT__"] = json.dumps(
            self._snapshot(run)["project_context"],
            ensure_ascii=False,
            sort_keys=True,
        )
        grounding["__GENERATION_COMMAND__"] = json.dumps(
            self._snapshot_command(run), ensure_ascii=False, sort_keys=True
        )
        return grounding

    def _snapshot_inputs_changed(self, run: AIRun) -> bool:
        snapshot = self._snapshot(run)
        requirement_snapshot = snapshot["requirement"]
        requirement = self.repo.requirement_internal(run.tenant_id, run.requirement_id)
        if (
            requirement.revision != requirement_snapshot["revision"]
            or requirement.semantic_hash != requirement_snapshot["semantic_hash"]
        ):
            return True

        project = self.repo.project_internal(run.tenant_id, run.project_id)
        if (
            project.knowledge_pack_id != snapshot["knowledge_pack_id"]
            or project.knowledge_pack_version != snapshot["knowledge_pack_version"]
        ):
            return True

        context = self.repo.project_context_internal(run.tenant_id, run.project_id)
        context_snapshot = snapshot["project_context"]
        if (
            context.revision != context_snapshot["revision"]
            or semantic_hash(context.summary, context.constraints_json)
            != semantic_hash(
                context_snapshot.get("summary", ""), context_snapshot.get("items", {})
            )
        ):
            return True

        current_knowledge = [
            {
                "id": item.id,
                "item_type": item.item_type,
                "code": item.code,
                "title": item.title,
                "content": item.content,
                "parent_code": item.parent_code,
                "metadata": item.metadata_json,
            }
            for item in (
                self.repo.knowledge_items(run.tenant_id, snapshot["knowledge_pack_id"])
                if snapshot["knowledge_pack_id"]
                else []
            )
        ]
        if semantic_hash(current_knowledge) != snapshot["knowledge_content_hash"]:
            return True

        source = snapshot.get("source")
        if not isinstance(source, dict):
            return False
        if source["type"] == "ANALYSIS":
            current = self.repo.analysis_internal(run.tenant_id, source["id"])
            if any(
                (
                    current.status != AssetStatus.APPROVED,
                    current.asset_revision != source["asset_revision"],
                    current.semantic_hash != source["semantic_hash"],
                    current.source_requirement_revision
                    != source["source_requirement_revision"],
                )
            ):
                return True
            assertions = {item.id: item for item in self.repo.assertions(run.tenant_id, current.id)}
            for captured in source["assertions"]:
                item = assertions.get(captured["id"])
                if item is None or semantic_hash(
                    item.code, item.text, item.constraint_json, item.source_span
                ) != semantic_hash(
                    captured["code"],
                    captured["text"],
                    captured["constraint"],
                    captured["source_span"],
                ):
                    return True
            return False
        if source["type"] == "RISK_BATCH":
            batch = self.repo.risk_batch_internal(run.tenant_id, source["id"])
            if (
                batch.revision != source["revision"]
                or batch.status != source["status"]
                or batch.source_analysis_id != source["source_analysis_id"]
            ):
                return True
            risks = {item.id: item for item in self.repo.risks(run.tenant_id, batch.id)}
            for captured in source["risks"]:
                item = risks.get(captured["id"])
                if item is None or any(
                    (
                        item.status != AssetStatus.APPROVED,
                        item.asset_revision != captured["asset_revision"],
                        item.semantic_hash != captured["semantic_hash"],
                    )
                ):
                    return True
            return False
        if source["type"] == "SCENARIO_BATCH":
            batch = self.repo.scenario_batch_internal(run.tenant_id, source["id"])
            if batch.revision != source["revision"] or batch.status != source["status"]:
                return True
            scenarios = {
                item.id: item for item in self.repo.scenarios(run.tenant_id, batch.id)
            }
            for captured in source["scenarios"]:
                item = scenarios.get(captured["id"])
                if item is None or any(
                    (
                        item.status != AssetStatus.APPROVED,
                        item.asset_revision != captured["asset_revision"],
                        item.semantic_hash != captured["semantic_hash"],
                    )
                ):
                    return True
            return False
        raise AppError(
            422,
            "AI_RUN_SNAPSHOT_INVALID",
            "AI run snapshot contains an unknown source type.",
        )

    def _add_references(
        self,
        run: AIRun,
        project_id: str,
        asset_type: str,
        asset_id: str,
        codes: list[str],
    ) -> None:
        items = {
            item["code"]: item
            for item in self._snapshot(run).get("knowledge_items", [])
        }
        for code in codes:
            item = items.get(code)
            if item is not None:
                self.repo.add(
                    KnowledgeReference(
                        tenant_id=run.tenant_id,
                        project_id=project_id,
                        asset_type=asset_type,
                        asset_id=asset_id,
                        knowledge_item_id=item["id"],
                        reference_code=item["code"],
                        excerpt=item["content"],
                        relevance=f"Used by deterministic {asset_type.lower()} generation.",
                    )
                )

    def _relation(
        self,
        tenant_id: str,
        project_id: str,
        from_type: str,
        from_id: str,
        relation_type: str,
        to_type: str,
        to_id: str,
    ) -> None:
        self.repo.add(
            AssetRelation(
                tenant_id=tenant_id,
                project_id=project_id,
                from_type=from_type,
                from_id=from_id,
                relation_type=relation_type,
                to_type=to_type,
                to_id=to_id,
            )
        )

    def _reference_reads(
        self, tenant_id: str, asset_type: str, asset_id: str
    ) -> list[KnowledgeReferenceRead]:
        return [
            KnowledgeReferenceRead.model_validate(item)
            for item in self.repo.references(tenant_id, asset_type, asset_id)
        ]

    def _pack_read(self, tenant_id: str, pack: Any) -> KnowledgePackRead:
        counts: dict[str, int] = {}
        for item in self.repo.knowledge_items(tenant_id, pack.id):
            counts[item.item_type] = counts.get(item.item_type, 0) + 1
        return KnowledgePackRead.model_validate(pack).model_copy(
            update={
                "description": "Versioned structured product and testing knowledge.",
                "summary": counts,
            }
        )

    def _project_read(self, actor: Actor, project: Project) -> ProjectRead:
        product = (
            self.repo.product_type_by_id(actor.tenant_id, project.product_type_id)
            if project.product_type_id
            else None
        )
        context = self.repo.project_context(actor, project.id)
        return ProjectRead.model_validate(project).model_copy(
            update={
                "product_type": ProductTypeRead.model_validate(product) if product else None,
                "context_revision": context.revision,
            }
        )

    def _risk_read(self, tenant_id: str, item: Risk) -> RiskRead:
        return RiskRead.model_validate(item).model_copy(
            update={
                "knowledge_references": self._reference_reads(
                    tenant_id, "RISK", item.id
                )
            }
        )

    def _scenario_read(self, tenant_id: str, item: Scenario) -> ScenarioRead:
        return ScenarioRead.model_validate(item).model_copy(
            update={
                "knowledge_references": self._reference_reads(
                    tenant_id, "SCENARIO", item.id
                )
            }
        )

    def _test_case_read(self, tenant_id: str, item: TestCase) -> TestCaseRead:
        return TestCaseRead.model_validate(item).model_copy(
            update={
                "steps": [
                    TestStepRead.model_validate(step)
                    for step in self.repo.steps(tenant_id, item.id)
                ],
                "knowledge_references": self._reference_reads(
                    tenant_id, "TEST_CASE", item.id
                ),
            }
        )

    @staticmethod
    def _asset_summary(item: Any | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            "id": item.id,
            "status": item.status,
            "revision": getattr(item, "asset_revision", None),
        }

    @staticmethod
    def _batch_summary(batch: Any | None, items: list[Any]) -> dict[str, Any] | None:
        if batch is None:
            return None
        return {
            "id": batch.id,
            "status": batch.status,
            "revision": batch.revision,
            "item_count": len(items),
            "approved_count": sum(
                1 for item in items if item.status == AssetStatus.APPROVED
            ),
        }

    @staticmethod
    def _ratio(covered: int, total: int) -> RatioMetric:
        percent = round((covered / total * 100.0), 2) if total else 0.0
        return RatioMetric(covered=covered, total=total, percent=percent)
