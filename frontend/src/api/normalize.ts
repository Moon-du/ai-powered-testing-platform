import type {
  AiRun,
  CoverageMetric,
  CoverageResponse,
  ExpectedBehaviorStatus,
  KnowledgeContextSummary,
  KnowledgePack,
  KnowledgeReference,
  ProductType,
  Project,
  ProjectContextItem,
  ProjectContextResponse,
  Requirement,
  RequirementAnalysis,
  RequirementRisk,
  ReviewStatus,
  RiskBatch,
  ScenarioBatch,
  TestCase,
  TestCaseBatch,
  TestCaseStep,
  TestScenario,
  TraceabilityResponse,
  WorkflowAssetRef,
  WorkflowState,
} from '@/types'

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {}
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asOptionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function normalizeReviewStatus(value: unknown): ReviewStatus {
  const allowed: ReviewStatus[] = [
    'AI_DRAFT',
    'HUMAN_EDITED',
    'APPROVED',
    'REJECTED',
    'SUPERSEDED',
    'STALE',
  ]
  return allowed.includes(value as ReviewStatus) ? (value as ReviewStatus) : 'AI_DRAFT'
}

function normalizeExpectedStatus(value: unknown, expectedResult?: unknown): ExpectedBehaviorStatus {
  if (value === 'REQUIREMENT_CLARIFICATION_REQUIRED') return 'CLARIFICATION_REQUIRED'
  if (value === 'DEFINED' || value === 'CLARIFICATION_REQUIRED' || value === 'UNDEFINED') {
    return value
  }
  return typeof expectedResult === 'string' && expectedResult ? 'DEFINED' : 'CLARIFICATION_REQUIRED'
}

export function normalizeProductType(value: unknown): ProductType {
  const raw = asRecord(value)
  const name = asString(raw.name, asString(raw.code, 'Unknown Product'))
  return {
    id: asString(raw.id),
    code: asString(raw.code),
    name,
    display_name: asString(raw.display_name, name),
    description: asOptionalString(raw.description),
    status: asString(raw.status, 'Active'),
  }
}

export function normalizeKnowledgePack(value: unknown): KnowledgePack {
  const raw = asRecord(value)
  const summary = asRecord(raw.summary)
  return {
    id: asString(raw.id),
    product_type_id: asOptionalString(raw.product_type_id),
    name: asString(raw.name, 'Knowledge Pack'),
    version: asString(raw.version, '1.0'),
    description: asOptionalString(raw.description),
    status: asString(raw.status, 'Published'),
    summary: Object.keys(summary).length
      ? Object.fromEntries(Object.entries(summary).map(([key, count]) => [key, asNumber(count)]))
      : undefined,
  }
}

export function normalizeProject(value: unknown): Project {
  const raw = asRecord(value)
  const productType = Object.keys(asRecord(raw.product_type)).length
    ? normalizeProductType(raw.product_type)
    : undefined
  return {
    id: asString(raw.id),
    project_code: asString(raw.project_code),
    name: asString(raw.name, 'Unnamed Project'),
    description: asOptionalString(raw.description),
    product_type_id: asOptionalString(raw.product_type_id),
    product_type: productType,
    knowledge_pack_id: asOptionalString(raw.knowledge_pack_id),
    knowledge_pack_version: asOptionalString(raw.knowledge_pack_version),
    product_variant: asOptionalString(raw.product_variant),
    project_version: asOptionalString(raw.project_version),
    status: asString(raw.status, 'Active'),
    context_revision: asNumber(raw.context_revision, 0),
    created_at: asOptionalString(raw.created_at),
    updated_at: asOptionalString(raw.updated_at),
  }
}

export function normalizeRequirement(value: unknown): Requirement {
  const raw = asRecord(value)
  return {
    id: asString(raw.id),
    project_id: asString(raw.project_id),
    requirement_code: asString(raw.requirement_code, asString(raw.code)),
    title: asOptionalString(raw.title),
    original_text: asString(raw.original_text),
    requirement_type: asOptionalString(raw.requirement_type),
    priority: asOptionalString(raw.priority),
    criticality: asOptionalString(raw.criticality),
    revision: asNumber(raw.revision, 1),
    status: asString(raw.status, 'Active'),
    review_status: raw.review_status ? normalizeReviewStatus(raw.review_status) : null,
    workflow_stage: asOptionalString(raw.workflow_stage),
    has_gaps: Boolean(raw.has_gaps),
    stale: Boolean(raw.stale),
    created_at: asOptionalString(raw.created_at),
    updated_at: asOptionalString(raw.updated_at),
  }
}

export function normalizeProjectContext(value: unknown, projectId: string): ProjectContextResponse {
  const raw = asRecord(value)
  const items = raw.items
  let normalizedItems: ProjectContextItem[] = []

  if (Array.isArray(items)) {
    normalizedItems = items.map((item) => {
      const entry = asRecord(item)
      return {
        id: asOptionalString(entry.id),
        context_type: asString(entry.context_type, 'Configuration'),
        name: asString(entry.name, 'Context'),
        value: typeof entry.value === 'string' ? entry.value : asRecord(entry.value),
        description: asOptionalString(entry.description),
        priority: asOptionalString(entry.priority),
        status: asOptionalString(entry.status),
      }
    })
  } else {
    normalizedItems = Object.entries(asRecord(items)).map(([key, source]) => {
      const entry = asRecord(source)
      const hasStructuredShape = 'value' in entry || 'context_type' in entry || 'name' in entry
      return {
        context_type: hasStructuredShape
          ? asString(entry.context_type, key.replaceAll('_', ' '))
          : key.replaceAll('_', ' '),
        name: hasStructuredShape ? asString(entry.name, key) : key,
        value: hasStructuredShape
          ? typeof entry.value === 'string'
            ? entry.value
            : asRecord(entry.value)
          : typeof source === 'string'
            ? source
            : asRecord(source),
        description: hasStructuredShape ? asOptionalString(entry.description) : undefined,
        priority: hasStructuredShape ? asOptionalString(entry.priority) : undefined,
        status: hasStructuredShape ? asOptionalString(entry.status) : 'Active',
      }
    })
  }

  return {
    project_id: asString(raw.project_id, projectId),
    revision: asNumber(raw.revision, 1),
    items: normalizedItems,
  }
}

export function serializeProjectContext(items: ProjectContextItem[]): Record<string, unknown> {
  return Object.fromEntries(
    items.map((item, index) => {
      const key = item.name.trim() || `${item.context_type.replaceAll(' ', '_').toLocaleLowerCase()}_${index + 1}`
      return [
        key,
        {
          context_type: item.context_type,
          name: item.name,
          value: item.value,
          description: item.description ?? null,
          priority: item.priority ?? null,
          status: item.status ?? 'Active',
        },
      ]
    }),
  )
}

export function normalizeKnowledgeContext(value: unknown): KnowledgeContextSummary {
  const raw = asRecord(value)
  const pack = asRecord(raw.knowledge_pack)
  const counts = asRecord(raw.counts)
  const itemCounts = asRecord(raw.item_counts)
  return {
    knowledge_pack_id: asOptionalString(raw.knowledge_pack_id) ?? asOptionalString(pack.id),
    knowledge_pack_version:
      asOptionalString(raw.knowledge_pack_version) ?? asOptionalString(pack.version),
    summary: Object.fromEntries(
      Object.entries(asRecord(raw.summary)).map(([key, count]) => [key, asNumber(count)]),
    ),
    counts: Object.fromEntries(
      Object.entries(Object.keys(counts).length ? counts : itemCounts).map(([key, count]) => [
        key,
        asNumber(count),
      ]),
    ),
    modules: asArray(raw.modules).map(asRecord),
    functions: asArray(raw.functions).map(asRecord),
    risks: asArray(raw.risks).map(asRecord),
    rules: asArray(raw.rules).map(asRecord),
    patterns: asArray(raw.patterns).map(asRecord),
    failure_modes: asArray(raw.failure_modes).map(asRecord),
    items: asArray(raw.items).map((value) => {
      const item = asRecord(value)
      return {
        id: asString(item.id),
        item_type: asString(item.item_type),
        code: asString(item.code),
        title: asString(item.title),
        content: asString(item.content),
        parent_code: asOptionalString(item.parent_code),
      }
    }),
  }
}

function normalizeKnowledgeReferences(value: unknown): KnowledgeReference[] {
  return asArray(value).map((item) => {
    const raw = asRecord(item)
    const score = typeof raw.relevance_score === 'number' ? raw.relevance_score : undefined
    return {
      knowledge_type: asString(raw.knowledge_type, asString(raw.asset_type, 'knowledge')),
      knowledge_id: asString(
        raw.knowledge_id,
        asString(raw.reference_code, asString(raw.knowledge_item_id)),
      ),
      knowledge_version: asOptionalString(raw.knowledge_version),
      usage_type: asOptionalString(raw.usage_type),
      reason: asString(raw.reason, asString(raw.excerpt, 'Referenced by generation')),
      relevance_score: score,
    }
  })
}

export function normalizeAnalysis(value: unknown): RequirementAnalysis {
  const raw = asRecord(value)
  return {
    id: asString(raw.id),
    requirement_id: asString(raw.requirement_id),
    analysis_version: asNumber(raw.analysis_version, asNumber(raw.asset_revision, 1)),
    revision: asNumber(raw.revision, asNumber(raw.asset_revision, 1)),
    summary: asString(raw.summary),
    intent: asOptionalString(raw.intent),
    testability: asOptionalString(raw.testability),
    assumptions: asArray(raw.assumptions).map((item) => asString(item)).filter(Boolean),
    ambiguities: asArray(raw.ambiguities ?? raw.ambiguities_json).map(asRecord),
    missing_information: asArray(raw.missing_information).map(asRecord),
    assertions: asArray(raw.assertions).map(asRecord),
    questions: asArray(raw.questions).map(asRecord),
    primary_function_id: asOptionalString(raw.primary_function_id),
    affected_module_ids: asArray(raw.affected_module_ids).map((item) => asString(item)).filter(Boolean),
    affected_function_ids: asArray(raw.affected_function_ids).map((item) => asString(item)).filter(Boolean),
    dependencies: asArray(raw.dependencies).map(asRecord),
    knowledge_references: normalizeKnowledgeReferences(raw.knowledge_references),
    review_status: normalizeReviewStatus(raw.review_status ?? raw.status),
    rejection_reason: asOptionalString(raw.rejection_reason),
    rejection_note: asOptionalString(raw.rejection_note),
  }
}

function normalizeRisk(value: unknown): RequirementRisk {
  const raw = asRecord(value)
  return {
    id: asString(raw.id),
    risk_code: asString(raw.risk_code, asString(raw.code)),
    title: asString(raw.title),
    description: asString(raw.description),
    severity: asOptionalString(raw.severity ?? raw.impact),
    likelihood: asOptionalString(raw.likelihood),
    priority: asOptionalString(raw.priority ?? raw.impact),
    rationale: asString(raw.rationale, asString(raw.why_generated)),
    requirement_gap: Boolean(raw.requirement_gap),
    review_status: normalizeReviewStatus(raw.review_status ?? raw.status),
    revision: asNumber(raw.revision, asNumber(raw.asset_revision, 1)),
    knowledge_references: normalizeKnowledgeReferences(raw.knowledge_references),
    rejection_reason: asOptionalString(raw.rejection_reason),
    rejection_note: asOptionalString(raw.rejection_note),
  }
}

export function normalizeRiskBatch(value: unknown): RiskBatch {
  const raw = asRecord(value)
  return {
    id: asString(raw.id),
    version: asNumber(raw.version, asNumber(raw.revision, 1)),
    review_status: normalizeReviewStatus(raw.review_status ?? raw.status),
    risks: asArray(raw.risks ?? raw.items).map(normalizeRisk),
    source_analysis_id: asOptionalString(raw.source_analysis_id),
  }
}

function normalizeScenario(value: unknown): TestScenario {
  const raw = asRecord(value)
  return {
    id: asString(raw.id),
    scenario_code: asString(raw.scenario_code, asString(raw.code)),
    title: asString(raw.title),
    scenario_type: asString(raw.scenario_type, asString(raw.category, 'NOMINAL')),
    test_intent: asString(raw.test_intent, asString(raw.intent)),
    generation_reason: asString(raw.generation_reason, asString(raw.why_generated)),
    expected_behavior_summary: asOptionalString(raw.expected_behavior_summary ?? raw.expected_result),
    expected_behavior_status: normalizeExpectedStatus(
      raw.expected_behavior_status ?? raw.expected_result_status,
      raw.expected_behavior_summary ?? raw.expected_result,
    ),
    priority: asOptionalString(raw.priority),
    mandatory: Boolean(raw.mandatory),
    review_status: normalizeReviewStatus(raw.review_status ?? raw.status),
    revision: asNumber(raw.revision, asNumber(raw.asset_revision, 1)),
    knowledge_references: normalizeKnowledgeReferences(raw.knowledge_references),
    blocking_questions: asArray(raw.blocking_questions ?? raw.blocking_questions_json)
      .map((item) => asString(item))
      .filter(Boolean),
    preconditions: asArray(raw.preconditions ?? raw.preconditions_json).map((item) => asString(item)).filter(Boolean),
    rejection_reason: asOptionalString(raw.rejection_reason),
    rejection_note: asOptionalString(raw.rejection_note),
  }
}

export function normalizeScenarioBatch(value: unknown): ScenarioBatch {
  const raw = asRecord(value)
  return {
    id: asString(raw.id),
    version: asNumber(raw.version, asNumber(raw.revision, 1)),
    review_status: normalizeReviewStatus(raw.review_status ?? raw.status),
    scenarios: asArray(raw.scenarios ?? raw.items).map(normalizeScenario),
    source_risk_batch_id: asOptionalString(raw.source_risk_batch_id),
  }
}

function normalizeTestCaseStep(value: unknown): TestCaseStep {
  const raw = asRecord(value)
  const expectedResult = asOptionalString(raw.expected_result)
  return {
    id: asOptionalString(raw.id),
    step_no: asNumber(raw.step_no, asNumber(raw.sequence, 1)),
    action: asString(raw.action),
    configuration: raw.configuration ?? raw.configuration_json,
    test_data: raw.test_data ?? raw.test_data_json,
    expected_result: expectedResult,
    expected_result_status: normalizeExpectedStatus(raw.expected_result_status, expectedResult),
    note: asOptionalString(raw.note),
  }
}

function normalizeTestCase(value: unknown): TestCase {
  const raw = asRecord(value)
  const expectedResult = raw.expected_summary ?? raw.expected_result
  return {
    id: asString(raw.id),
    test_case_code: asString(raw.test_case_code, asString(raw.code)),
    title: asString(raw.title, asString(raw.objective)),
    objective: asOptionalString(raw.objective),
    priority: asString(raw.priority, 'MEDIUM'),
    scenario_id: asString(raw.scenario_id),
    expected_result_status: normalizeExpectedStatus(raw.expected_result_status, expectedResult),
    expected_result: asOptionalString(expectedResult),
    generation_reason: asString(raw.generation_reason, asString(raw.why_generated)),
    preconditions: asArray(raw.preconditions ?? raw.preconditions_json)
      .map((item) => asString(item))
      .filter(Boolean),
    configuration: raw.configuration ?? raw.configuration_json,
    test_data: raw.test_data ?? raw.test_data_json,
    review_status: normalizeReviewStatus(raw.review_status ?? raw.status),
    revision: asNumber(raw.revision, asNumber(raw.asset_revision, 1)),
    steps: asArray(raw.steps).map(normalizeTestCaseStep),
    knowledge_references: normalizeKnowledgeReferences(raw.knowledge_references),
    blocking_questions: asArray(raw.blocking_questions ?? raw.blocking_questions_json)
      .map((item) => asString(item))
      .filter(Boolean),
    rejection_reason: asOptionalString(raw.rejection_reason),
    rejection_note: asOptionalString(raw.rejection_note),
  }
}

export function normalizeTestCaseBatch(value: unknown): TestCaseBatch {
  const raw = asRecord(value)
  return {
    id: asString(raw.id),
    version: asNumber(raw.version, asNumber(raw.revision, 1)),
    review_status: normalizeReviewStatus(raw.review_status ?? raw.status),
    test_cases: asArray(raw.test_cases ?? raw.items).map(normalizeTestCase),
    source_scenario_batch_id: asOptionalString(raw.source_scenario_batch_id),
  }
}

export function normalizeAiRun(value: unknown): AiRun {
  const raw = asRecord(value)
  const result = asRecord(raw.result)
  const resultId = asOptionalString(raw.result_id) ?? asOptionalString(result.id)
  const resultType = asOptionalString(raw.result_type) ?? asOptionalString(result.type)
  const rawError = asRecord(raw.error)
  const errorMessage = asOptionalString(raw.error_message) ?? asOptionalString(rawError.message)
  return {
    id: asString(raw.id),
    task_type: asString(raw.task_type, asString(raw.run_type, 'AI_GENERATION')),
    status: (asString(raw.status, 'QUEUED') as AiRun['status']),
    progress: Object.keys(asRecord(raw.progress)).length
      ? {
          stage: asOptionalString(asRecord(raw.progress).stage),
          percent: asNumber(asRecord(raw.progress).percent),
        }
      : null,
    result: resultId ? { type: resultType ?? 'asset', id: resultId } : null,
    error: errorMessage
      ? {
          code: asString(raw.error_code, asString(rawError.code, 'AI_RUN_FAILED')),
          message: errorMessage,
          retryable: Boolean(raw.retryable ?? rawError.retryable),
        }
      : null,
  }
}

export function normalizeWorkflow(value: unknown, requirementId: string): WorkflowState {
  const raw = asRecord(value)
  const activeRaw = asRecord(raw.active_assets)
  const activeAssets: Record<string, WorkflowAssetRef | null> = {}
  for (const [key, item] of Object.entries(activeRaw)) {
    if (!item) {
      activeAssets[key] = null
      continue
    }
    const asset = asRecord(item)
    activeAssets[key] = {
      type: asString(asset.type, key.toLocaleUpperCase()),
      id: asString(asset.id),
      version: asNumber(asset.version, asNumber(asset.revision, 1)),
      review_status: normalizeReviewStatus(asset.review_status ?? asset.status),
    }
  }

  const explicitStage = asOptionalString(raw.current_stage)
  let stage = explicitStage
  const hasStale = Object.values(activeAssets).some((item) => item?.review_status === 'STALE')
  if (!stage && hasStale) stage = 'STALE'
  if (!stage && activeAssets.test_case_batch) {
    stage = activeAssets.test_case_batch.review_status === 'APPROVED' ? 'READY' : 'TESTCASE_REVIEW'
  }
  if (!stage && activeAssets.scenario_batch) stage = 'SCENARIO_REVIEW'
  if (!stage && activeAssets.risk_batch) stage = 'RISK_REVIEW'
  if (!stage && activeAssets.analysis) {
    stage = activeAssets.analysis.review_status === 'APPROVED' ? 'RISK_REVIEW' : 'ANALYSIS_REVIEW'
  }
  const runs = asArray(raw.runs).map(normalizeAiRun)
  if (!stage && runs.some((run) => run.status === 'QUEUED' || run.status === 'RUNNING')) {
    stage = 'ANALYZING'
  }
  stage ??= 'IMPORTED'

  return {
    requirement_id: asString(raw.requirement_id, requirementId),
    current_stage: stage,
    stages: asArray(raw.stages).map((item) => {
      const entry = asRecord(item)
      return { name: asString(entry.name), status: asString(entry.status) }
    }),
    active_assets: activeAssets,
    available_actions: asArray(raw.available_actions)
      .map((item) => asString(item))
      .filter(Boolean) as WorkflowState['available_actions'],
    blocking_reasons: asArray(raw.blocking_reasons ?? raw.blockers).map((item) => {
      const entry = asRecord(item)
      return {
        code: asString(entry.code, 'WORKFLOW_BLOCKED'),
        message: asString(entry.message, '工作流需要处理阻塞项'),
      }
    }),
  }
}

export function normalizeTraceability(value: unknown): TraceabilityResponse {
  const raw = asRecord(value)
  return {
    nodes: asArray(raw.nodes).map((item) => {
      const node = asRecord(item)
      return {
        type: asString(node.type),
        id: asString(node.id),
        label: asString(node.label, asString(node.code, asString(node.title))),
        status: asOptionalString(node.status),
      }
    }),
    relations: asArray(raw.relations ?? raw.edges).map((item) => {
      const edge = asRecord(item)
      return {
        source: asString(edge.source, asString(edge.from_id)),
        relation: asString(edge.relation, asString(edge.relation_type)),
        target: asString(edge.target, asString(edge.to_id)),
      }
    }),
  }
}

function normalizeCoverageMetric(value: unknown): CoverageMetric {
  const raw = asRecord(value)
  return {
    total: asNumber(raw.total),
    covered: raw.covered == null ? undefined : asNumber(raw.covered),
    analyzed: raw.analyzed == null ? undefined : asNumber(raw.analyzed),
    approved: raw.approved == null ? undefined : asNumber(raw.approved),
    percentage:
      raw.percentage == null && raw.percent == null
        ? undefined
        : asNumber(raw.percentage, asNumber(raw.percent)),
  }
}

export function normalizeCoverage(value: unknown): CoverageResponse {
  const raw = asRecord(value)
  const issues = asRecord(raw.issues)
  return {
    requirements: normalizeCoverageMetric(raw.requirements),
    assertion_coverage: normalizeCoverageMetric(raw.assertion_coverage ?? raw.assertions),
    risk_coverage: normalizeCoverageMetric(raw.risk_coverage ?? raw.risks),
    scenario: normalizeCoverageMetric(raw.scenario ?? raw.scenarios),
    test_cases: normalizeCoverageMetric(raw.test_cases ?? raw.cases),
    issues: {
      requirement_gaps: asNumber(issues.requirement_gaps),
      undefined_expected_behaviors: asNumber(
        issues.undefined_expected_behaviors,
        asNumber(issues.clarification_required),
      ),
      stale_assets: asNumber(issues.stale_assets),
    },
  }
}
