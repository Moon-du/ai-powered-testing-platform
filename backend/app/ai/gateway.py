from __future__ import annotations

import json
import base64
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.config import Settings
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

    def extract_image_text(self, content: bytes, media_type: str) -> str:
        ...


DraftT = TypeVar("DraftT", bound=BaseModel)


class DeepSeekLLMGateway:
    """OpenAI-compatible DeepSeek gateway with strict structured-output parsing."""

    def __init__(self, settings: Settings) -> None:
        self.api_key = (
            settings.llm_api_key.get_secret_value().strip()
            if settings.llm_api_key is not None
            else ""
        )
        self.model = settings.llm_model
        self.vision_model = settings.llm_vision_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.client = httpx.Client(
            base_url=settings.llm_base_url.rstrip("/"),
            timeout=settings.llm_timeout_seconds,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    def analyze(self, requirement_text: str, knowledge: dict[str, str]) -> AnalysisDraft:
        payload = self._complete(
            task="Analyze the immutable requirement into atomic, traceable assertions.",
            schema=AnalysisDraft.model_json_schema(),
            inputs={"requirement_text": requirement_text, "knowledge": knowledge},
            rules=[
                "Every assertion source_span must be an exact contiguous substring of requirement_text.",
                "Do not invent product behavior. Record missing behavior as an ambiguity.",
                "Use only knowledge reference codes that exist in the supplied knowledge object.",
            ],
        )
        return self._validate(AnalysisDraft, payload)

    def generate_risks(
        self, analysis: AnalysisDraft, knowledge: dict[str, str]
    ) -> list[RiskDraft]:
        return self._complete_list(
            RiskDraft,
            task="Generate requirement-derived product and test risks.",
            inputs={"analysis": analysis.model_dump(mode="json"), "knowledge": knowledge},
            rules=[
                "Each risk assertion_code must match an assertion code in analysis.",
                "Do not invent product behavior; mark requirement_gap when behavior is unspecified.",
                "Return at least one material risk.",
            ],
        )

    def generate_scenarios(
        self, risks: list[RiskDraft], knowledge: dict[str, str]
    ) -> list[ScenarioDraft]:
        return self._complete_list(
            ScenarioDraft,
            task="Generate executable test scenarios for the approved risks.",
            inputs={
                "risks": [item.model_dump(mode="json") for item in risks],
                "knowledge": knowledge,
            },
            rules=[
                "Each scenario risk_code must match a supplied risk code.",
                "When expected behavior is absent, use CLARIFICATION_REQUIRED, expected_result null, and blocking_questions.",
                "Do not convert an assumption into a defined expected result.",
            ],
        )

    def generate_test_cases(
        self, scenarios: list[ScenarioDraft], knowledge: dict[str, str]
    ) -> list[TestCaseDraft]:
        return self._complete_list(
            TestCaseDraft,
            task="Generate detailed, execution-ready test cases from approved scenarios.",
            inputs={
                "scenarios": [item.model_dump(mode="json") for item in scenarios],
                "knowledge": knowledge,
            },
            rules=[
                "Each test case scenario_code must match a supplied scenario code.",
                "Include concrete configuration, ordered steps, and non-empty test_data for every step.",
                "Preserve CLARIFICATION_REQUIRED where the scenario lacks a defined expected result.",
            ],
        )

    def extract_image_text(self, content: bytes, media_type: str) -> str:
        if not self.api_key:
            raise AppError(503, "LLM_NOT_CONFIGURED", "LLM_API_KEY is required for image extraction.")
        encoded = base64.b64encode(content).decode("ascii")
        try:
            response = self.client.post(
                "/chat/completions",
                json={
                    "model": self.vision_model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all product and testing knowledge from this image faithfully. Return plain text only."},
                            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}},
                        ],
                    }],
                    "temperature": 0,
                    "stream": False,
                },
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AppError(502, "IMAGE_EXTRACTION_FAILED", "DeepSeek could not extract the uploaded image.") from exc

    def _complete_list(
        self,
        model: type[DraftT],
        *,
        task: str,
        inputs: dict[str, Any],
        rules: list[str],
    ) -> list[DraftT]:
        payload = self._complete(
            task=task,
            schema={
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": model.model_json_schema()}
                },
                "required": ["items"],
                "additionalProperties": False,
            },
            inputs=inputs,
            rules=rules,
        )
        try:
            return TypeAdapter(list[model]).validate_python(payload["items"])
        except (KeyError, TypeError, ValidationError) as exc:
            raise AppError(502, "AI_OUTPUT_INVALID", "DeepSeek returned an invalid structured response.") from exc

    @staticmethod
    def _validate(model: type[DraftT], payload: Any) -> DraftT:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise AppError(502, "AI_OUTPUT_INVALID", "DeepSeek returned an invalid structured response.") from exc

    def _complete(
        self,
        *,
        task: str,
        schema: dict[str, Any],
        inputs: dict[str, Any],
        rules: list[str],
    ) -> dict[str, Any]:
        if not self.api_key:
            raise AppError(
                503,
                "LLM_NOT_CONFIGURED",
                "LLM_API_KEY is required for DeepSeek AI generation.",
            )
        system_prompt = (
            "You are a senior test engineer. Return one JSON object only, without Markdown. "
            "Follow the JSON schema exactly. Never fabricate requirements, expected behavior, "
            "knowledge references, or approvals. Preserve the language used by the requirement."
        )
        user_prompt = json.dumps(
            {"task": task, "rules": rules, "json_schema": schema, "inputs": inputs},
            ensure_ascii=False,
        )
        try:
            response = self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "stream": False,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise TypeError("Expected a JSON object")
            return payload
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AppError(502, "LLM_REQUEST_FAILED", "DeepSeek API request or response parsing failed.") from exc


def build_llm_gateway(settings: Settings) -> LLMGateway:
    if settings.llm_provider == "deepseek":
        return DeepSeekLLMGateway(settings)
    raise AppError(503, "LLM_NOT_CONFIGURED", f"Unsupported LLM provider: {settings.llm_provider}")


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

    def extract_image_text(self, content: bytes, media_type: str) -> str:
        return "Image extraction test content."


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
