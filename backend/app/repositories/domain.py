from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from app.dependencies import Actor
from app.errors import not_found
from app.models import (
    AIRun,
    Analysis,
    AssetRelation,
    KnowledgeItem,
    KnowledgePack,
    KnowledgeReference,
    ProductType,
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

ModelT = TypeVar("ModelT")


class DomainRepository:
    """All application reads and writes cross this tenant-aware boundary."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        return instance

    def add_all(self, instances: Iterable[object]) -> None:
        self.session.add_all(list(instances))

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def begin_nested(self):
        return self.session.begin_nested()

    def product_type(self, tenant_id: str, code: str) -> ProductType:
        item = self.session.scalar(
            select(ProductType).where(
                ProductType.tenant_id == tenant_id, ProductType.code == code
            )
        )
        if item is None:
            raise not_found("ProductType", code)
        return item

    def list_product_types(self, tenant_id: str) -> list[ProductType]:
        return list(
            self.session.scalars(
                select(ProductType)
                .where(ProductType.tenant_id == tenant_id)
                .order_by(ProductType.code)
            )
        )

    def product_type_by_id(self, tenant_id: str, product_type_id: str) -> ProductType:
        item = self.session.scalar(
            select(ProductType).where(
                ProductType.id == product_type_id,
                ProductType.tenant_id == tenant_id,
            )
        )
        if item is None:
            raise not_found("ProductType", product_type_id)
        return item

    def knowledge_pack(
        self, tenant_id: str, product_type_id: str, version: str
    ) -> KnowledgePack:
        item = self.session.scalar(
            select(KnowledgePack).where(
                KnowledgePack.tenant_id == tenant_id,
                KnowledgePack.product_type_id == product_type_id,
                KnowledgePack.version == version,
                KnowledgePack.status == "PUBLISHED",
            )
        )
        if item is None:
            raise not_found("KnowledgePack", version)
        return item

    def list_knowledge_packs(
        self, tenant_id: str, product_type_id: str
    ) -> list[KnowledgePack]:
        return list(
            self.session.scalars(
                select(KnowledgePack)
                .where(
                    KnowledgePack.tenant_id == tenant_id,
                    KnowledgePack.product_type_id == product_type_id,
                )
                .order_by(KnowledgePack.version)
            )
        )

    def knowledge_pack_by_id(self, tenant_id: str, pack_id: str) -> KnowledgePack:
        item = self.session.scalar(
            select(KnowledgePack).where(
                KnowledgePack.id == pack_id, KnowledgePack.tenant_id == tenant_id
            )
        )
        if item is None:
            raise not_found("KnowledgePack", pack_id)
        return item

    def knowledge_items(self, tenant_id: str, pack_id: str) -> list[KnowledgeItem]:
        return list(
            self.session.scalars(
                select(KnowledgeItem)
                .where(
                    KnowledgeItem.tenant_id == tenant_id,
                    KnowledgeItem.knowledge_pack_id == pack_id,
                )
                .order_by(KnowledgeItem.code)
            )
        )

    def knowledge_items_by_codes(
        self, tenant_id: str, pack_id: str, codes: Iterable[str]
    ) -> dict[str, KnowledgeItem]:
        code_set = set(codes)
        if not code_set:
            return {}
        items = self.session.scalars(
            select(KnowledgeItem).where(
                KnowledgeItem.tenant_id == tenant_id,
                KnowledgeItem.knowledge_pack_id == pack_id,
                KnowledgeItem.code.in_(code_set),
            )
        )
        return {item.code: item for item in items}

    def list_projects(self, actor: Actor) -> list[Project]:
        return list(
            self.session.scalars(
                select(Project)
                .join(
                    ProjectMembership,
                    and_(
                        ProjectMembership.project_id == Project.id,
                        ProjectMembership.tenant_id == Project.tenant_id,
                    ),
                )
                .where(
                    Project.tenant_id == actor.tenant_id,
                    ProjectMembership.user_id == actor.user_id,
                )
                .order_by(Project.created_at)
            )
        )

    def require_project(self, actor: Actor, project_id: str) -> Project:
        project = self.session.scalar(
            select(Project)
            .join(
                ProjectMembership,
                and_(
                    ProjectMembership.project_id == Project.id,
                    ProjectMembership.tenant_id == Project.tenant_id,
                ),
            )
            .where(
                Project.id == project_id,
                Project.tenant_id == actor.tenant_id,
                ProjectMembership.user_id == actor.user_id,
            )
        )
        if project is None:
            raise not_found("Project", project_id)
        return project

    def project_internal(self, tenant_id: str, project_id: str) -> Project:
        project = self.session.scalar(
            select(Project).where(
                Project.id == project_id, Project.tenant_id == tenant_id
            )
        )
        if project is None:
            raise not_found("Project", project_id)
        return project

    def project_context(self, actor: Actor, project_id: str) -> ProjectContext:
        self.require_project(actor, project_id)
        context = self.session.scalar(
            select(ProjectContext).where(
                ProjectContext.project_id == project_id,
                ProjectContext.tenant_id == actor.tenant_id,
            )
        )
        if context is None:
            raise not_found("ProjectContext", project_id)
        return context

    def project_context_internal(
        self, tenant_id: str, project_id: str
    ) -> ProjectContext:
        context = self.session.scalar(
            select(ProjectContext).where(
                ProjectContext.project_id == project_id,
                ProjectContext.tenant_id == tenant_id,
            )
        )
        if context is None:
            raise not_found("ProjectContext", project_id)
        return context

    def membership(self, actor: Actor, project_id: str) -> ProjectMembership:
        self.require_project(actor, project_id)
        membership = self.session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.tenant_id == actor.tenant_id,
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == actor.user_id,
            )
        )
        if membership is None:
            raise not_found("ProjectMembership", actor.user_id)
        return membership

    def memberships(self, actor: Actor, project_id: str) -> list[ProjectMembership]:
        self.require_project(actor, project_id)
        return list(
            self.session.scalars(
                select(ProjectMembership)
                .where(
                    ProjectMembership.tenant_id == actor.tenant_id,
                    ProjectMembership.project_id == project_id,
                )
                .order_by(ProjectMembership.created_at)
            )
        )

    def list_requirements(self, actor: Actor, project_id: str) -> list[Requirement]:
        self.require_project(actor, project_id)
        return list(
            self.session.scalars(
                select(Requirement)
                .where(
                    Requirement.tenant_id == actor.tenant_id,
                    Requirement.project_id == project_id,
                )
                .order_by(Requirement.created_at)
            )
        )

    def requirement(self, actor: Actor, requirement_id: str) -> Requirement:
        requirement = self.session.scalar(
            select(Requirement)
            .join(
                ProjectMembership,
                and_(
                    ProjectMembership.project_id == Requirement.project_id,
                    ProjectMembership.tenant_id == Requirement.tenant_id,
                ),
            )
            .where(
                Requirement.id == requirement_id,
                Requirement.tenant_id == actor.tenant_id,
                ProjectMembership.user_id == actor.user_id,
            )
        )
        if requirement is None:
            raise not_found("Requirement", requirement_id)
        return requirement

    def requirement_internal(self, tenant_id: str, requirement_id: str) -> Requirement:
        requirement = self.session.scalar(
            select(Requirement).where(
                Requirement.id == requirement_id, Requirement.tenant_id == tenant_id
            )
        )
        if requirement is None:
            raise not_found("Requirement", requirement_id)
        return requirement

    def lock_requirement_for_run(
        self, tenant_id: str, requirement_id: str
    ) -> None:
        """Serialize run admission per requirement on databases with row locks."""

        locked_id = self.session.scalar(
            select(Requirement.id)
            .where(
                Requirement.id == requirement_id,
                Requirement.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if locked_id is None:
            raise not_found("Requirement", requirement_id)

    def requirement_revisions(
        self, tenant_id: str, requirement_id: str
    ) -> list[RequirementRevision]:
        return list(
            self.session.scalars(
                select(RequirementRevision)
                .where(
                    RequirementRevision.tenant_id == tenant_id,
                    RequirementRevision.requirement_id == requirement_id,
                )
                .order_by(RequirementRevision.revision)
            )
        )

    def analyses(self, tenant_id: str, requirement_id: str) -> list[Analysis]:
        return list(
            self.session.scalars(
                select(Analysis)
                .where(
                    Analysis.tenant_id == tenant_id,
                    Analysis.requirement_id == requirement_id,
                )
                .order_by(Analysis.asset_revision)
            )
        )

    def analysis(self, actor: Actor, analysis_id: str) -> Analysis:
        item = self._scoped_asset(actor, Analysis, analysis_id)
        if item is None:
            raise not_found("Analysis", analysis_id)
        return item

    def analysis_internal(self, tenant_id: str, analysis_id: str) -> Analysis:
        item = self.session.scalar(
            select(Analysis).where(
                Analysis.id == analysis_id, Analysis.tenant_id == tenant_id
            )
        )
        if item is None:
            raise not_found("Analysis", analysis_id)
        return item

    def assertions(self, tenant_id: str, analysis_id: str) -> list[RequirementAssertion]:
        return list(
            self.session.scalars(
                select(RequirementAssertion)
                .where(
                    RequirementAssertion.tenant_id == tenant_id,
                    RequirementAssertion.analysis_id == analysis_id,
                )
                .order_by(RequirementAssertion.code)
            )
        )

    def risk_batches(self, tenant_id: str, requirement_id: str) -> list[RiskBatch]:
        return list(
            self.session.scalars(
                select(RiskBatch)
                .where(
                    RiskBatch.tenant_id == tenant_id,
                    RiskBatch.requirement_id == requirement_id,
                )
                .order_by(RiskBatch.revision)
            )
        )

    def risk_batch(self, actor: Actor, batch_id: str) -> RiskBatch:
        item = self._scoped_asset(actor, RiskBatch, batch_id)
        if item is None:
            raise not_found("RiskBatch", batch_id)
        return item

    def risk_batch_internal(self, tenant_id: str, batch_id: str) -> RiskBatch:
        item = self.session.scalar(
            select(RiskBatch).where(
                RiskBatch.id == batch_id, RiskBatch.tenant_id == tenant_id
            )
        )
        if item is None:
            raise not_found("RiskBatch", batch_id)
        return item

    def risks(self, tenant_id: str, batch_id: str) -> list[Risk]:
        return list(
            self.session.scalars(
                select(Risk)
                .where(Risk.tenant_id == tenant_id, Risk.batch_id == batch_id)
                .order_by(Risk.code)
            )
        )

    def risk(self, actor: Actor, risk_id: str) -> Risk:
        item = self._scoped_asset(actor, Risk, risk_id)
        if item is None:
            raise not_found("Risk", risk_id)
        return item

    def scenario_batches(
        self, tenant_id: str, requirement_id: str
    ) -> list[ScenarioBatch]:
        return list(
            self.session.scalars(
                select(ScenarioBatch)
                .where(
                    ScenarioBatch.tenant_id == tenant_id,
                    ScenarioBatch.requirement_id == requirement_id,
                )
                .order_by(ScenarioBatch.revision)
            )
        )

    def scenario_batch(self, actor: Actor, batch_id: str) -> ScenarioBatch:
        item = self._scoped_asset(actor, ScenarioBatch, batch_id)
        if item is None:
            raise not_found("ScenarioBatch", batch_id)
        return item

    def scenario_batch_internal(self, tenant_id: str, batch_id: str) -> ScenarioBatch:
        item = self.session.scalar(
            select(ScenarioBatch).where(
                ScenarioBatch.id == batch_id, ScenarioBatch.tenant_id == tenant_id
            )
        )
        if item is None:
            raise not_found("ScenarioBatch", batch_id)
        return item

    def scenarios(self, tenant_id: str, batch_id: str) -> list[Scenario]:
        return list(
            self.session.scalars(
                select(Scenario)
                .where(Scenario.tenant_id == tenant_id, Scenario.batch_id == batch_id)
                .order_by(Scenario.code)
            )
        )

    def scenarios_for_risk(self, tenant_id: str, risk_id: str) -> list[Scenario]:
        return list(
            self.session.scalars(
                select(Scenario).where(
                    Scenario.tenant_id == tenant_id, Scenario.risk_id == risk_id
                )
            )
        )

    def scenario(self, actor: Actor, scenario_id: str) -> Scenario:
        item = self._scoped_asset(actor, Scenario, scenario_id)
        if item is None:
            raise not_found("Scenario", scenario_id)
        return item

    def test_case_batches(
        self, tenant_id: str, requirement_id: str
    ) -> list[TestCaseBatch]:
        return list(
            self.session.scalars(
                select(TestCaseBatch)
                .where(
                    TestCaseBatch.tenant_id == tenant_id,
                    TestCaseBatch.requirement_id == requirement_id,
                )
                .order_by(TestCaseBatch.revision)
            )
        )

    def test_case_batch(self, actor: Actor, batch_id: str) -> TestCaseBatch:
        item = self._scoped_asset(actor, TestCaseBatch, batch_id)
        if item is None:
            raise not_found("TestCaseBatch", batch_id)
        return item

    def test_case_batch_internal(self, tenant_id: str, batch_id: str) -> TestCaseBatch:
        item = self.session.scalar(
            select(TestCaseBatch).where(
                TestCaseBatch.id == batch_id, TestCaseBatch.tenant_id == tenant_id
            )
        )
        if item is None:
            raise not_found("TestCaseBatch", batch_id)
        return item

    def test_cases(self, tenant_id: str, batch_id: str) -> list[TestCase]:
        return list(
            self.session.scalars(
                select(TestCase)
                .where(TestCase.tenant_id == tenant_id, TestCase.batch_id == batch_id)
                .order_by(TestCase.code)
            )
        )

    def test_cases_for_scenario(
        self, tenant_id: str, scenario_id: str
    ) -> list[TestCase]:
        return list(
            self.session.scalars(
                select(TestCase).where(
                    TestCase.tenant_id == tenant_id,
                    TestCase.scenario_id == scenario_id,
                )
            )
        )

    def test_case(self, actor: Actor, test_case_id: str) -> TestCase:
        item = self._scoped_asset(actor, TestCase, test_case_id)
        if item is None:
            raise not_found("TestCase", test_case_id)
        return item

    def steps(self, tenant_id: str, test_case_id: str) -> list[TestStep]:
        return list(
            self.session.scalars(
                select(TestStep)
                .where(
                    TestStep.tenant_id == tenant_id,
                    TestStep.test_case_id == test_case_id,
                )
                .order_by(TestStep.sequence)
            )
        )

    def ai_run(self, actor: Actor, run_id: str) -> AIRun:
        item = self._scoped_asset(actor, AIRun, run_id)
        if item is None:
            raise not_found("AIRun", run_id)
        return item

    def ai_run_internal(self, tenant_id: str, run_id: str) -> AIRun:
        item = self.session.scalar(
            select(AIRun).where(AIRun.id == run_id, AIRun.tenant_id == tenant_id)
        )
        if item is None:
            raise not_found("AIRun", run_id)
        return item

    def claim_ai_run(self, tenant_id: str, run_id: str, started_at) -> bool:
        result = self.session.execute(
            update(AIRun)
            .where(
                AIRun.id == run_id,
                AIRun.tenant_id == tenant_id,
                AIRun.status == "QUEUED",
            )
            .values(status="RUNNING", started_at=started_at)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def ai_run_by_key(
        self,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        run_type: str,
        key: str,
    ) -> AIRun | None:
        return self.session.scalar(
            select(AIRun).where(
                AIRun.tenant_id == tenant_id,
                AIRun.project_id == project_id,
                AIRun.actor_id == actor_id,
                AIRun.run_type == run_type,
                AIRun.idempotency_key == key,
            )
        )

    def active_ai_run(
        self, tenant_id: str, requirement_id: str, run_type: str
    ) -> AIRun | None:
        return self.session.scalar(
            select(AIRun)
            .where(
                AIRun.tenant_id == tenant_id,
                AIRun.requirement_id == requirement_id,
                AIRun.run_type == run_type,
                AIRun.status.in_(["QUEUED", "RUNNING"]),
            )
            .order_by(AIRun.created_at.desc())
        )

    def ai_runs_for_requirement(
        self, tenant_id: str, requirement_id: str
    ) -> list[AIRun]:
        return list(
            self.session.scalars(
                select(AIRun)
                .where(
                    AIRun.tenant_id == tenant_id,
                    AIRun.requirement_id == requirement_id,
                )
                .order_by(AIRun.created_at.desc())
            )
        )

    def references(
        self, tenant_id: str, asset_type: str, asset_id: str
    ) -> list[KnowledgeReference]:
        return list(
            self.session.scalars(
                select(KnowledgeReference).where(
                    KnowledgeReference.tenant_id == tenant_id,
                    KnowledgeReference.asset_type == asset_type,
                    KnowledgeReference.asset_id == asset_id,
                )
            )
        )

    def project_relations(self, actor: Actor, project_id: str) -> list[AssetRelation]:
        self.require_project(actor, project_id)
        return list(
            self.session.scalars(
                select(AssetRelation).where(
                    AssetRelation.tenant_id == actor.tenant_id,
                    AssetRelation.project_id == project_id,
                )
            )
        )

    def project_assets(self, actor: Actor, project_id: str) -> dict[str, list[object]]:
        self.require_project(actor, project_id)
        tenant = actor.tenant_id
        scoped = lambda model: list(
            self.session.scalars(
                select(model).where(
                    model.tenant_id == tenant, model.project_id == project_id
                )
            )
        )
        return {
            "requirements": scoped(Requirement),
            "assertions": scoped(RequirementAssertion),
            "analyses": scoped(Analysis),
            "risk_batches": scoped(RiskBatch),
            "risks": scoped(Risk),
            "scenario_batches": scoped(ScenarioBatch),
            "scenarios": scoped(Scenario),
            "test_case_batches": scoped(TestCaseBatch),
            "test_cases": scoped(TestCase),
        }

    def next_revision(self, model: type, tenant_id: str, requirement_id: str, field) -> int:
        current = self.session.scalar(
            select(func.max(field)).where(
                model.tenant_id == tenant_id, model.requirement_id == requirement_id
            )
        )
        return int(current or 0) + 1

    def _scoped_asset(self, actor: Actor, model: type[ModelT], asset_id: str) -> ModelT | None:
        return self.session.scalar(
            select(model)
            .join(
                ProjectMembership,
                and_(
                    ProjectMembership.project_id == model.project_id,
                    ProjectMembership.tenant_id == model.tenant_id,
                ),
            )
            .where(
                model.id == asset_id,
                model.tenant_id == actor.tenant_id,
                ProjectMembership.user_id == actor.user_id,
            )
        )
