export type ReviewStatus =
  | 'AI_DRAFT'
  | 'HUMAN_EDITED'
  | 'APPROVED'
  | 'REJECTED'
  | 'SUPERSEDED'
  | 'STALE'

export type ExpectedBehaviorStatus = 'DEFINED' | 'CLARIFICATION_REQUIRED' | 'UNDEFINED'

export type ProjectRole = 'OWNER' | 'EDITOR' | 'REVIEWER' | 'VIEWER'

export type WorkflowAction =
  | 'ANALYZE_REQUIREMENT'
  | 'GENERATE_RISKS'
  | 'GENERATE_SCENARIOS'
  | 'GENERATE_TEST_CASES'
  | 'REGENERATE_ANALYSIS'
  | 'REGENERATE_RISKS'
  | 'REGENERATE_SCENARIOS'
  | 'REGENERATE_TEST_CASES'
  | 'REVIEW_ANALYSIS'
  | 'REVIEW_RISKS'
  | 'REVIEW_SCENARIOS'
  | 'REVIEW_TEST_CASES'

export type WorkflowStage =
  | 'IMPORTED'
  | 'ANALYZING'
  | 'ANALYSIS_REVIEW'
  | 'RISK_REVIEW'
  | 'SCENARIO_REVIEW'
  | 'TESTCASE_REVIEW'
  | 'READY'
  | 'STALE'
  | 'BLOCKED'

export interface ProductType {
  id: string
  code: string
  name: string
  display_name: string
  description?: string | null
  status: string
}

export interface KnowledgePack {
  id: string
  product_type_id: string
  name: string
  version: string
  description?: string | null
  status: string
  summary?: Record<string, number>
}

export interface Project {
  id: string
  project_code: string
  name: string
  description?: string | null
  product_type_id: string
  product_type?: ProductType
  knowledge_pack_id: string
  knowledge_pack_version: string
  product_variant?: string | null
  project_version?: string | null
  status: string
  context_revision?: number
  created_at?: string
  updated_at?: string
}

export interface ProjectContextItem {
  id?: string
  context_type: string
  name: string
  value: string | Record<string, unknown>
  description?: string | null
  priority?: string | null
  status?: string
}

export interface ProjectContextResponse {
  project_id: string
  revision: number
  items: ProjectContextItem[]
}

export interface KnowledgeContextSummary {
  knowledge_pack_id?: string
  knowledge_pack_version?: string
  summary?: Record<string, number>
  counts?: Record<string, number>
  modules?: Array<Record<string, unknown>>
  functions?: Array<Record<string, unknown>>
  risks?: Array<Record<string, unknown>>
  rules?: Array<Record<string, unknown>>
  patterns?: Array<Record<string, unknown>>
  failure_modes?: Array<Record<string, unknown>>
}

export interface Requirement {
  id: string
  project_id: string
  requirement_code: string
  title?: string | null
  original_text: string
  requirement_type?: string | null
  priority?: string | null
  criticality?: string | null
  revision: number
  status: string
  review_status?: ReviewStatus | null
  workflow_stage?: WorkflowStage | string | null
  has_gaps?: boolean
  stale?: boolean
  created_at?: string
  updated_at?: string
}

export interface KnowledgeReference {
  knowledge_type: string
  knowledge_id: string
  knowledge_version?: string | null
  usage_type?: string | null
  reason: string
  relevance_score?: number | null
}

export interface WorkflowAssetRef {
  type: string
  id: string
  version?: number
  review_status?: ReviewStatus
}

export interface WorkflowState {
  requirement_id: string
  current_stage: string
  stages: Array<{ name: string; status: string }>
  active_assets: Record<string, WorkflowAssetRef | null>
  available_actions: WorkflowAction[]
  blocking_reasons?: Array<{ code: string; message: string }>
}

export interface AiRun {
  id: string
  task_type: string
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
  progress?: { stage?: string; percent?: number } | null
  result?: { type: string; id: string } | null
  error?: { code: string; message: string; retryable: boolean } | null
}

export interface RequirementAnalysis {
  id: string
  requirement_id: string
  analysis_version: number
  revision: number
  summary: string
  intent?: string | null
  testability?: string | null
  assumptions?: string[]
  ambiguities?: Array<Record<string, unknown>>
  missing_information?: Array<Record<string, unknown>>
  assertions?: Array<Record<string, unknown>>
  questions?: Array<Record<string, unknown>>
  primary_function_id?: string | null
  affected_module_ids?: string[]
  affected_function_ids?: string[]
  dependencies?: Array<Record<string, unknown>>
  knowledge_references?: KnowledgeReference[]
  review_status: ReviewStatus
}

export interface RequirementRisk {
  id: string
  risk_code: string
  title: string
  description: string
  severity?: string
  likelihood?: string
  priority?: string
  rationale: string
  requirement_gap: boolean
  review_status: ReviewStatus
  revision: number
  knowledge_references?: KnowledgeReference[]
}

export interface TestScenario {
  id: string
  scenario_code: string
  title: string
  scenario_type: string
  test_intent: string
  generation_reason: string
  expected_behavior_summary?: string | null
  expected_behavior_status: ExpectedBehaviorStatus
  priority?: string
  mandatory?: boolean
  review_status: ReviewStatus
  revision: number
  knowledge_references?: KnowledgeReference[]
  blocking_questions?: string[]
}

export interface TestCaseStep {
  id?: string
  step_no: number
  action: string
  configuration?: unknown
  test_data?: unknown
  expected_result?: string | null
  expected_result_status: ExpectedBehaviorStatus
  note?: string | null
}

export interface TestCase {
  id: string
  test_case_code: string
  title: string
  priority: string
  scenario_id: string
  expected_result_status?: ExpectedBehaviorStatus
  generation_reason?: string
  objective?: string | null
  preconditions?: string[]
  configuration?: unknown
  test_data?: unknown
  review_status: ReviewStatus
  revision: number
  steps: TestCaseStep[]
  knowledge_references?: KnowledgeReference[]
  blocking_questions?: string[]
}

export interface RiskBatch {
  id: string
  version: number
  review_status?: ReviewStatus
  risks: RequirementRisk[]
  source_analysis_id?: string
}

export interface ScenarioBatch {
  id: string
  version: number
  review_status?: ReviewStatus
  scenarios: TestScenario[]
  source_risk_batch_id?: string
}

export interface TestCaseBatch {
  id: string
  version: number
  review_status?: ReviewStatus
  test_cases: TestCase[]
  source_scenario_batch_id?: string
}

export interface TraceabilityNode {
  type: string
  id: string
  label?: string
  status?: string
}

export interface TraceabilityRelation {
  source: string
  relation: string
  target: string
}

export interface TraceabilityResponse {
  nodes: TraceabilityNode[]
  relations: TraceabilityRelation[]
}

export interface CoverageMetric {
  total: number
  covered?: number
  analyzed?: number
  approved?: number
  percentage?: number
}

export interface CoverageResponse {
  requirements: CoverageMetric
  assertion_coverage: CoverageMetric
  risk_coverage: CoverageMetric
  scenario: CoverageMetric
  test_cases: CoverageMetric
  issues: {
    requirement_gaps: number
    undefined_expected_behaviors: number
    stale_assets: number
  }
}
