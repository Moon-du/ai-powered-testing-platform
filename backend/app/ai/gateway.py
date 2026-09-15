from __future__ import annotations

from typing import Protocol

from app.errors import AppError
from app.schemas.domain import (
    AnalysisDraft,
    AssertionDraft,
    ConstraintSpec,
    ExpectedResultStatus,
    RiskDraft,
    ScenarioDraft,
    StepDraft,
    TestCaseDraft,
)


def _has_structured_content(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, list):
        return bool(value) and any(_has_structured_content(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and any(
            _has_structured_content(item) for item in value.values()
        )
    return False


class LLMGateway(Protocol):
    """Typed boundary. Implementations never receive a database session."""

    def analyze(self, requirement_text: str, knowledge: dict[str, str]) -> AnalysisDraft:
        ...

    def generate_risks(
        self, analysis: AnalysisDraft, knowledge: dict[str, str]
    ) -> list[RiskDraft]:
        ...

    def generate_scenarios(
        self, risks: list[RiskDraft], knowledge: dict[str, str]
    ) -> list[ScenarioDraft]:
        ...

    def generate_test_cases(
        self, scenarios: list[ScenarioDraft], knowledge: dict[str, str]
    ) -> list[TestCaseDraft]:
        ...


class FakeLLMGateway:
    """Deterministic, reviewable Electronic Pipette development provider."""

    def analyze(self, requirement_text: str, knowledge: dict[str, str]) -> AnalysisDraft:
        return AnalysisDraft(
            summary=(
                "The requirement defines an operator-set dispensing volume with an "
                "inclusive supported interval of 10 µL through 300 µL."
            ),
            assertions=[
                AssertionDraft(
                    code="A01",
                    text="The user can configure dispensing volume from 10 µL to 300 µL inclusive.",
                    constraint=ConstraintSpec(
                        minimum=10,
                        maximum=300,
                        unit="µL",
                        inclusive_minimum=True,
                        inclusive_maximum=True,
                    ),
                    source_span=requirement_text,
                )
            ],
            ambiguities=[
                {
                    "code": "AMB-OUT-OF-RANGE",
                    "description": "Behavior for values outside the supported range is not specified.",
                    "blocking": True,
                }
            ],
            why_generated=(
                "The atomic assertion preserves the requirement wording while making the "
                "numeric interval explicit for downstream boundary analysis."
            ),
            knowledge_reference_codes=["FUNC-VOLUME-SETTING", "DEP-VOLUME-CALCULATION"],
        )

    def generate_risks(
        self, analysis: AnalysisDraft, knowledge: dict[str, str]
    ) -> list[RiskDraft]:
        return [
            RiskDraft(
                code="RISK-BOUNDARY",
                assertion_code="A01",
                title="Incorrect boundary acceptance",
                description=(
                    "The pipette may reject supported endpoint values or accept a volume "
                    "outside 10–300 µL, leading to an incorrect configured dispense."
                ),
                likelihood="MEDIUM",
                impact="HIGH",
                rationale="The numeric range creates explicit minimum and maximum boundaries.",
                requirement_gap=False,
                why_generated=(
                    "Derived from assertion A01 and boundary-value rule TR-001."
                ),
                knowledge_reference_codes=["TR-001", "RP-INCORRECT-CONFIGURATION"],
            ),
            RiskDraft(
                code="RISK-PERSISTENCE",
                assertion_code="A01",
                title="Configured volume is not retained",
                description=(
                    "A valid configured volume may be lost or changed after a power cycle."
                ),
                likelihood="LOW",
                impact="HIGH",
                rationale=(
                    "Volume-setting state participates in subsequent calculation and motor control."
                ),
                requirement_gap=True,
                why_generated=(
                    "Derived from the volume-setting dependency chain and persistence failure mode."
                ),
                knowledge_reference_codes=["TR-002", "FM-PERSISTENCE-FAILURE"],
            ),
        ]

    def generate_scenarios(
        self, risks: list[RiskDraft], knowledge: dict[str, str]
    ) -> list[ScenarioDraft]:
        risk_codes = {risk.code for risk in risks}
        scenarios: list[ScenarioDraft] = []
        if "RISK-BOUNDARY" in risk_codes:
            defined = [
                (
                    "SCN-NOMINAL",
                    "Set a nominal volume",
                    "Nominal",
                    "Configure 150 µL and verify the selected setting.",
                    "The displayed and active dispensing volume is 150 µL.",
                ),
                (
                    "SCN-MIN",
                    "Set the minimum supported volume",
                    "Min",
                    "Configure the inclusive minimum value of 10 µL.",
                    "The displayed and active dispensing volume is 10 µL.",
                ),
                (
                    "SCN-MAX",
                    "Set the maximum supported volume",
                    "Max",
                    "Configure the inclusive maximum value of 300 µL.",
                    "The displayed and active dispensing volume is 300 µL.",
                ),
            ]
            for code, title, category, intent, expected in defined:
                scenarios.append(
                    ScenarioDraft(
                        code=code,
                        risk_code="RISK-BOUNDARY",
                        title=title,
                        intent=intent,
                        category=category,
                        preconditions=["Electronic pipette is powered on and ready."],
                        expected_result=expected,
                        expected_result_status=ExpectedResultStatus.DEFINED,
                        why_generated="Boundary partition derived from A01 and TR-001.",
                        knowledge_reference_codes=["TR-001"],
                    )
                )
            scenarios.extend(
                [
                    ScenarioDraft(
                        code="SCN-BELOW",
                        risk_code="RISK-BOUNDARY",
                        title="Enter a value below the supported range",
                        intent="Attempt to configure 9 µL and observe product behavior.",
                        category="Below",
                        preconditions=["Electronic pipette is powered on and ready."],
                        expected_result=None,
                        expected_result_status=ExpectedResultStatus.CLARIFICATION_REQUIRED,
                        blocking_questions=[
                            "Should 9 µL be rejected, clamped to 10 µL, or handled another way?"
                        ],
                        why_generated=(
                            "TR-001 requires a below-minimum partition, but the requirement "
                            "does not define its expected behavior."
                        ),
                        knowledge_reference_codes=["TR-001"],
                    ),
                    ScenarioDraft(
                        code="SCN-ABOVE",
                        risk_code="RISK-BOUNDARY",
                        title="Enter a value above the supported range",
                        intent="Attempt to configure 301 µL and observe product behavior.",
                        category="Above",
                        preconditions=["Electronic pipette is powered on and ready."],
                        expected_result=None,
                        expected_result_status=ExpectedResultStatus.CLARIFICATION_REQUIRED,
                        blocking_questions=[
                            "Should 301 µL be rejected, clamped to 300 µL, or handled another way?"
                        ],
                        why_generated=(
                            "TR-001 requires an above-maximum partition, but the requirement "
                            "does not define its expected behavior."
                        ),
                        knowledge_reference_codes=["TR-001"],
                    ),
                ]
            )
        if "RISK-PERSISTENCE" in risk_codes:
            scenarios.append(
                ScenarioDraft(
                    code="SCN-PERSISTENCE",
                    risk_code="RISK-PERSISTENCE",
                    title="Retain a configured volume after power cycle",
                    intent="Set 150 µL, power-cycle the pipette, and inspect the restored setting.",
                    category="Persistence",
                    preconditions=["Electronic pipette is powered on and ready."],
                    expected_result=None,
                    expected_result_status=ExpectedResultStatus.CLARIFICATION_REQUIRED,
                    blocking_questions=[
                        "Should the configured volume persist after power-cycle, and within what restoration time?"
                    ],
                    why_generated=(
                        "TR-002 identifies persistence as a test consideration, but the "
                        "requirement does not define persistence behavior."
                    ),
                    knowledge_reference_codes=["TR-002", "FM-PERSISTENCE-FAILURE"],
                )
            )
        return scenarios

    def generate_test_cases(
        self, scenarios: list[ScenarioDraft], knowledge: dict[str, str]
    ) -> list[TestCaseDraft]:
        cases: list[TestCaseDraft] = []
        for index, scenario in enumerate(scenarios, start=1):
            volume_by_scenario = {
                "SCN-NOMINAL": 150,
                "SCN-MIN": 10,
                "SCN-MAX": 300,
                "SCN-BELOW": 9,
                "SCN-ABOVE": 301,
                "SCN-PERSISTENCE": 150,
            }
            volume = volume_by_scenario.get(scenario.code)
            cases.append(
                TestCaseDraft(
                    code=f"TC-{index:03d}-{scenario.code}",
                    scenario_code=scenario.code,
                    title=f"Execute: {scenario.title}",
                    objective=scenario.intent,
                    preconditions=scenario.preconditions,
                    configuration={
                        "product": "Electronic Pipette",
                        "operating_mode": "VOLUME_SETTING",
                        "unit": "µL",
                    },
                    expected_result=scenario.expected_result,
                    expected_result_status=scenario.expected_result_status,
                    blocking_questions=scenario.blocking_questions,
                    steps=[
                        StepDraft(
                            sequence=1,
                            action="Power on the electronic pipette and open volume setting.",
                            expected_result="Volume setting is available.",
                            test_data={"power_state": "ON"},
                        ),
                        StepDraft(
                            sequence=2,
                            action=scenario.intent,
                            expected_result=scenario.expected_result,
                            test_data=(
                                {"configured_volume_uL": volume}
                                if volume is not None
                                else {}
                            ),
                        ),
                    ],
                    why_generated=(
                        f"Implements approved scenario {scenario.code} without adding new test intent."
                    ),
                    knowledge_reference_codes=scenario.knowledge_reference_codes,
                )
            )
        return cases


class DomainValidator:
    """Deterministic checks applied after Pydantic parsing and before persistence."""

    @staticmethod
    def analysis(draft: AnalysisDraft, source_text: str) -> None:
        codes = [item.code for item in draft.assertions]
        if len(codes) != len(set(codes)):
            raise AppError(422, "AI_OUTPUT_INVALID", "Assertion codes must be unique.")
        if any(item.source_span not in source_text for item in draft.assertions):
            raise AppError(
                422,
                "AI_OUTPUT_INVALID",
                "Assertion source spans must come from the immutable requirement text.",
            )

    @staticmethod
    def risks(drafts: list[RiskDraft], assertion_codes: set[str]) -> None:
        if not drafts or any(item.assertion_code not in assertion_codes for item in drafts):
            raise AppError(
                422, "AI_OUTPUT_INVALID", "Every risk must derive from a known assertion."
            )

    @staticmethod
    def scenarios(drafts: list[ScenarioDraft], risk_codes: set[str]) -> None:
        if not drafts or any(item.risk_code not in risk_codes for item in drafts):
            raise AppError(
                422, "AI_OUTPUT_INVALID", "Every scenario must validate an approved risk."
            )

    @staticmethod
    def test_cases(drafts: list[TestCaseDraft], scenario_codes: set[str]) -> None:
        if not drafts or any(item.scenario_code not in scenario_codes for item in drafts):
            raise AppError(
                422,
                "AI_OUTPUT_INVALID",
                "Every test case must implement an approved scenario.",
            )
        if any(
            not _has_structured_content(item.configuration)
            or not item.steps
            or any(
                not step.action.strip()
                or not _has_structured_content(step.test_data)
                or (
                    item.expected_result_status == ExpectedResultStatus.DEFINED
                    and (
                        step.expected_result is None
                        or not step.expected_result.strip()
                    )
                )
                for step in item.steps
            )
            for item in drafts
        ):
            raise AppError(
                422,
                "AI_OUTPUT_INVALID",
                "Generated test cases must include execution-ready configuration, actions, test data, and defined step results.",
            )
