from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    KnowledgeItem,
    KnowledgePack,
    ProductType,
    Project,
    ProjectContext,
    ProjectMembership,
    Requirement,
    RequirementRevision,
)

DEMO_TENANT_ID = "demo-tenant"
DEMO_USER_ID = "dev-user"
PRODUCT_TYPE_ID = "11111111-1111-4111-8111-111111111111"
PACK_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_ID = "33333333-3333-4333-8333-333333333333"
REQUIREMENT_ID = "44444444-4444-4444-8444-444444444444"

REQUIREMENT_TEXT = "User can configure dispensing volume from 10 µL to 300 µL."

KNOWLEDGE_ITEMS: tuple[tuple[str, str, str, str, str | None], ...] = (
    (
        "MODULE",
        "MODULE-VOLUME",
        "Volume Management",
        "Controls configuration, display, calculation, and actuation of dispensing volume.",
        None,
    ),
    (
        "FUNCTION",
        "FUNC-VOLUME-SETTING",
        "Volume Setting",
        "An operator configures a supported dispensing volume in microlitres.",
        "MODULE-VOLUME",
    ),
    (
        "DEPENDENCY",
        "DEP-VOLUME-CALCULATION",
        "Volume Calculation",
        "The configured value feeds volume calculation.",
        "FUNC-VOLUME-SETTING",
    ),
    (
        "DEPENDENCY",
        "DEP-MOTOR-CONTROL",
        "Motor Control",
        "Calculated volume controls motor actuation.",
        "FUNC-VOLUME-SETTING",
    ),
    (
        "DEPENDENCY",
        "DEP-UI-DISPLAY",
        "UI Display",
        "The selected volume is shown to the operator.",
        "FUNC-VOLUME-SETTING",
    ),
    (
        "TESTING_RULE",
        "TR-001",
        "Boundary Value Analysis",
        "Cover nominal, minimum, maximum, just-below, and just-above partitions.",
        "FUNC-VOLUME-SETTING",
    ),
    (
        "TESTING_RULE",
        "TR-002",
        "Power-cycle Persistence Check",
        "Ask whether the configured value must survive a power cycle; use the requirement as the authority for expected behavior.",
        "FUNC-VOLUME-SETTING",
    ),
    (
        "RISK_PATTERN",
        "RP-INCORRECT-CONFIGURATION",
        "Incorrect Configuration",
        "A supported value is rejected or an unsupported value is accepted.",
        "FUNC-VOLUME-SETTING",
    ),
    (
        "FAILURE_MODE",
        "FM-PERSISTENCE-FAILURE",
        "Persistence Failure",
        "A configured setting is lost or changed across a power cycle.",
        "FUNC-VOLUME-SETTING",
    ),
)


def _semantic_hash(*values: str) -> str:
    normalized = "\n".join(value.strip().casefold() for value in values)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def seed_demo(
    session: Session,
    tenant_id: str = DEMO_TENANT_ID,
    user_id: str = DEMO_USER_ID,
) -> None:
    product = session.scalar(
        select(ProductType).where(
            ProductType.tenant_id == tenant_id,
            ProductType.code == "ELECTRONIC_PIPETTE",
        )
    )
    if product is None:
        product = ProductType(
            id=PRODUCT_TYPE_ID if tenant_id == DEMO_TENANT_ID else None,
            tenant_id=tenant_id,
            code="ELECTRONIC_PIPETTE",
            name="Electronic Pipette",
            description="Programmable laboratory electronic pipette.",
        )
        session.add(product)
        session.flush()

    pack = session.scalar(
        select(KnowledgePack).where(
            KnowledgePack.tenant_id == tenant_id,
            KnowledgePack.product_type_id == product.id,
            KnowledgePack.version == "1.0",
        )
    )
    if pack is None:
        pack_content = "|".join(item[1] + item[3] for item in KNOWLEDGE_ITEMS)
        pack = KnowledgePack(
            id=PACK_ID if tenant_id == DEMO_TENANT_ID else None,
            tenant_id=tenant_id,
            product_type_id=product.id,
            name="Electronic Pipette Knowledge Pack",
            version="1.0",
            status="PUBLISHED",
            content_hash=hashlib.sha256(pack_content.encode("utf-8")).hexdigest(),
        )
        session.add(pack)
        session.flush()

    existing_codes = set(
        session.scalars(
            select(KnowledgeItem.code).where(
                KnowledgeItem.tenant_id == tenant_id,
                KnowledgeItem.knowledge_pack_id == pack.id,
            )
        )
    )
    for item_type, code, title, content, parent_code in KNOWLEDGE_ITEMS:
        if code not in existing_codes:
            session.add(
                KnowledgeItem(
                    tenant_id=tenant_id,
                    knowledge_pack_id=pack.id,
                    item_type=item_type,
                    code=code,
                    title=title,
                    content=content,
                    parent_code=parent_code,
                    metadata_json={"source": "Electronic Pipette Pack EP v1.0"},
                )
            )

    project = session.scalar(
        select(Project).where(
            Project.tenant_id == tenant_id,
            Project.project_code == "EP-DEMO",
        )
    )
    if project is None:
        project = Project(
            id=PROJECT_ID if tenant_id == DEMO_TENANT_ID else None,
            tenant_id=tenant_id,
            project_code="EP-DEMO",
            name="Electronic Pipette Demo",
            description="Deterministic P0 Electronic Pipette vertical slice.",
            product_type_id=product.id,
            knowledge_pack_id=pack.id,
            knowledge_pack_version=pack.version,
            product_variant="Electronic Pipette 10–300 µL",
            project_version="1.0",
            status="ACTIVE",
            owner=user_id,
            created_by=user_id,
        )
        session.add(project)
        session.flush()
        session.add(
            ProjectContext(
                tenant_id=tenant_id,
                project_id=project.id,
                summary="Electronic Pipette P0 validation context.",
                constraints_json={
                    "volume_unit": "µL",
                    "supported_volume": {"minimum": 10, "maximum": 300},
                    "llm_provider": "fake",
                },
            )
        )

    membership = session.scalar(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == tenant_id,
            ProjectMembership.project_id == project.id,
            ProjectMembership.user_id == user_id,
        )
    )
    if membership is None:
        session.add(
            ProjectMembership(
                tenant_id=tenant_id,
                project_id=project.id,
                user_id=user_id,
                role="OWNER",
            )
        )

    requirement = session.scalar(
        select(Requirement).where(
            Requirement.tenant_id == tenant_id,
            Requirement.project_id == project.id,
            Requirement.requirement_code == "EP-REQ-001",
        )
    )
    if requirement is None:
        value_hash = _semantic_hash("Volume setting", REQUIREMENT_TEXT)
        requirement = Requirement(
            id=REQUIREMENT_ID if tenant_id == DEMO_TENANT_ID else None,
            tenant_id=tenant_id,
            project_id=project.id,
            requirement_code="EP-REQ-001",
            title="Dispensing volume configuration",
            original_text=REQUIREMENT_TEXT,
            revision=1,
            semantic_hash=value_hash,
            created_by=user_id,
        )
        session.add(requirement)
        session.flush()
        session.add(
            RequirementRevision(
                tenant_id=tenant_id,
                project_id=project.id,
                requirement_id=requirement.id,
                revision=1,
                title=requirement.title,
                original_text=requirement.original_text,
                semantic_hash=value_hash,
                change_summary="Initial Electronic Pipette seed.",
                created_by=user_id,
            )
        )

    session.flush()


def main() -> None:
    with SessionLocal() as session:
        seed_demo(session)
        session.commit()


if __name__ == "__main__":
    main()
