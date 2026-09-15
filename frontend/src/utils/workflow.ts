import type {
  ExpectedBehaviorStatus,
  ReviewStatus,
  TestCase,
  TestScenario,
  WorkflowAction,
  WorkflowState,
} from '@/types'

export interface StatusPresentation {
  label: string
  color: string
}

const reviewStatusMap: Record<ReviewStatus, StatusPresentation> = {
  AI_DRAFT: { label: 'AI 草稿', color: 'blue' },
  HUMAN_EDITED: { label: '人工编辑', color: 'gold' },
  APPROVED: { label: '已批准', color: 'green' },
  REJECTED: { label: '已拒绝', color: 'red' },
  SUPERSEDED: { label: '已替代', color: 'default' },
  STALE: { label: '已过期', color: 'orange' },
}

const expectedStatusMap: Record<ExpectedBehaviorStatus, StatusPresentation> = {
  DEFINED: { label: '预期已定义', color: 'green' },
  CLARIFICATION_REQUIRED: { label: '需要澄清', color: 'orange' },
  UNDEFINED: { label: '预期未定义', color: 'red' },
}

export function reviewStatusPresentation(status?: ReviewStatus | null): StatusPresentation {
  return status ? reviewStatusMap[status] : { label: '未开始', color: 'default' }
}

export function expectedStatusPresentation(
  status?: ExpectedBehaviorStatus | null,
): StatusPresentation {
  return status ? expectedStatusMap[status] : { label: '未知', color: 'default' }
}

const activeAssetAliases: Record<string, string[]> = {
  analysis: ['analysis', 'requirement_analysis'],
  riskBatch: ['risk_batch', 'risks', 'riskBatch'],
  scenarioBatch: ['scenario_batch', 'scenarios', 'scenarioBatch'],
  testCaseBatch: ['testcase_batch', 'test_case_batch', 'test_cases', 'testCaseBatch'],
}

export function activeAssetId(
  workflow: WorkflowState | undefined,
  asset: keyof typeof activeAssetAliases,
): string | null {
  if (!workflow) return null
  for (const key of activeAssetAliases[asset]) {
    const value = workflow.active_assets?.[key]
    if (value?.id) return value.id
  }
  return null
}

export function hasWorkflowAction(
  workflow: WorkflowState | undefined,
  action: WorkflowAction,
): boolean {
  return workflow?.available_actions.includes(action) ?? false
}

const generationActions = new Set<WorkflowAction>([
  'ANALYZE_REQUIREMENT',
  'GENERATE_RISKS',
  'GENERATE_SCENARIOS',
  'GENERATE_TEST_CASES',
  'REGENERATE_ANALYSIS',
  'REGENERATE_RISKS',
  'REGENERATE_SCENARIOS',
  'REGENERATE_TEST_CASES',
])

export function canInvokeWorkflowAction(
  workflow: WorkflowState | undefined,
  action: WorkflowAction,
  generationInFlight = false,
): boolean {
  return (
    hasWorkflowAction(workflow, action) &&
    !(generationInFlight && generationActions.has(action))
  )
}

export function canGenerateTestCases(scenarios: TestScenario[]): boolean {
  return scenarios.some((scenario) => scenario.review_status === 'APPROVED')
}

export function countClarificationRequired(testCases: TestCase[]): number {
  return testCases.reduce((count, testCase) => {
    const caseNeedsClarification =
      testCase.expected_result_status === 'CLARIFICATION_REQUIRED' ||
      testCase.expected_result_status === 'UNDEFINED'
    const stepCount = testCase.steps.filter(
      (step) =>
        step.expected_result_status === 'CLARIFICATION_REQUIRED' ||
        step.expected_result_status === 'UNDEFINED',
    ).length
    return count + (caseNeedsClarification ? 1 : 0) + stepCount
  }, 0)
}

export function isTestCaseExecutionReady(testCase: TestCase): boolean {
  if (testCase.expected_result_status !== 'DEFINED') return false
  if (testCase.blocking_questions?.length) return false
  if (!hasStructuredContent(testCase.configuration)) return false
  if (!testCase.steps.length) return false
  return testCase.steps.every(
    (step) =>
      Boolean(step.action.trim()) &&
      hasStructuredContent(step.test_data) &&
      step.expected_result_status === 'DEFINED' && Boolean(step.expected_result?.trim()),
  )
}

function hasStructuredContent(value: unknown): boolean {
  if (value == null) return false
  if (typeof value === 'string') return Boolean(value.trim())
  if (typeof value === 'number' || typeof value === 'boolean') return true
  if (Array.isArray(value)) return value.length > 0 && value.some(hasStructuredContent)
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    return entries.length > 0 && entries.some(([, entry]) => hasStructuredContent(entry))
  }
  return false
}

export function approvableTestCaseIds(
  testCases: TestCase[],
  selectedIds: string[],
): string[] {
  const selected = new Set(selectedIds)
  return testCases
    .filter(
      (testCase) =>
        selected.has(testCase.id) &&
        !['APPROVED', 'STALE', 'SUPERSEDED'].includes(testCase.review_status) &&
        isTestCaseExecutionReady(testCase),
    )
    .map((testCase) => testCase.id)
}

export function clampPercent(value?: number | null): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(100, Math.max(0, Math.round(value ?? 0)))
}
