import type { TestCase, TestScenario, WorkflowState } from '@/types'
import {
  activeAssetId,
  approvableTestCaseIds,
  canInvokeWorkflowAction,
  canGenerateTestCases,
  clampPercent,
  countClarificationRequired,
  expectedStatusPresentation,
  hasWorkflowAction,
  isTestCaseExecutionReady,
  reviewStatusPresentation,
} from '@/utils/workflow'

describe('workflow helpers', () => {
  it('resolves backend active-asset aliases', () => {
    const workflow: WorkflowState = {
      requirement_id: 'REQ-1',
      current_stage: 'SCENARIO_REVIEW',
      stages: [],
      available_actions: [],
      active_assets: {
        requirement_analysis: { type: 'REQUIREMENT_ANALYSIS', id: 'RA-1' },
        scenario_batch: { type: 'SCENARIO_BATCH', id: 'SB-1' },
      },
    }

    expect(activeAssetId(workflow, 'analysis')).toBe('RA-1')
    expect(activeAssetId(workflow, 'scenarioBatch')).toBe('SB-1')
    expect(activeAssetId(workflow, 'riskBatch')).toBeNull()
  })

  it('enforces the approved-scenario generation gate', () => {
    const base: TestScenario = {
      id: 'SC-1',
      scenario_code: 'SC-1',
      title: 'Boundary',
      scenario_type: 'BOUNDARY',
      test_intent: 'Verify lower bound',
      generation_reason: 'Testing rule',
      expected_behavior_status: 'DEFINED',
      review_status: 'AI_DRAFT',
      revision: 1,
    }

    expect(canGenerateTestCases([base])).toBe(false)
    expect(canGenerateTestCases([{ ...base, review_status: 'APPROVED' }])).toBe(true)
  })

  it('uses server workflow actions as the authorization source of truth', () => {
    const workflow: WorkflowState = {
      requirement_id: 'REQ-1',
      current_stage: 'ANALYSIS_REVIEW',
      stages: [],
      active_assets: {},
      available_actions: ['REVIEW_ANALYSIS', 'REGENERATE_ANALYSIS'],
    }

    expect(hasWorkflowAction(workflow, 'REVIEW_ANALYSIS')).toBe(true)
    expect(hasWorkflowAction(workflow, 'REGENERATE_ANALYSIS')).toBe(true)
    expect(hasWorkflowAction(workflow, 'GENERATE_RISKS')).toBe(false)
    expect(hasWorkflowAction(undefined, 'ANALYZE_REQUIREMENT')).toBe(false)
    expect(canInvokeWorkflowAction(workflow, 'REGENERATE_ANALYSIS', true)).toBe(false)
    expect(canInvokeWorkflowAction(workflow, 'REVIEW_ANALYSIS', true)).toBe(true)
  })

  it('counts undefined case and step expectations', () => {
    const testCase: TestCase = {
      id: 'TC-1',
      test_case_code: 'TC-1',
      title: 'Below minimum',
      priority: 'HIGH',
      scenario_id: 'SC-1',
      expected_result_status: 'CLARIFICATION_REQUIRED',
      review_status: 'AI_DRAFT',
      revision: 1,
      steps: [
        {
          step_no: 1,
          action: 'Enter 9 µL',
          expected_result: null,
          expected_result_status: 'UNDEFINED',
        },
      ],
    }

    expect(countClarificationRequired([testCase])).toBe(2)
    expect(isTestCaseExecutionReady(testCase)).toBe(false)
  })

  it('approves only selected execution-ready cases from a mixed batch', () => {
    const ready: TestCase = {
      id: 'TC-READY',
      test_case_code: 'TC-READY',
      title: 'Nominal',
      priority: 'HIGH',
      scenario_id: 'SC-NOMINAL',
      expected_result_status: 'DEFINED',
      configuration: { mode: 'aspirate' },
      review_status: 'AI_DRAFT',
      revision: 1,
      steps: [
        {
          step_no: 1,
          action: 'Set 100 µL',
          test_data: { target_volume: '100 µL' },
          expected_result: '100 µL is displayed',
          expected_result_status: 'DEFINED',
        },
      ],
    }
    const clarification: TestCase = {
      ...ready,
      id: 'TC-CLARIFY',
      test_case_code: 'TC-CLARIFY',
      expected_result_status: 'CLARIFICATION_REQUIRED',
      blocking_questions: ['What happens after restart?'],
      steps: [
        {
          step_no: 1,
          action: 'Restart the device',
          expected_result: null,
          expected_result_status: 'CLARIFICATION_REQUIRED',
        },
      ],
    }

    expect(isTestCaseExecutionReady(ready)).toBe(true)
    expect(approvableTestCaseIds([ready, clarification], [ready.id, clarification.id])).toEqual([
      ready.id,
    ])
    expect(isTestCaseExecutionReady({ ...ready, configuration: {} })).toBe(false)
    expect(
      isTestCaseExecutionReady({
        ...ready,
        steps: [{ ...ready.steps[0]!, test_data: {} }],
      }),
    ).toBe(false)
    expect(
      isTestCaseExecutionReady({
        ...ready,
        steps: [{ ...ready.steps[0]!, action: '   ' }],
      }),
    ).toBe(false)
  })

  it('maps statuses and safely clamps progress', () => {
    expect(reviewStatusPresentation('STALE').label).toBe('已过期')
    expect(expectedStatusPresentation('CLARIFICATION_REQUIRED').color).toBe('orange')
    expect(clampPercent(143.2)).toBe(100)
    expect(clampPercent(-4)).toBe(0)
    expect(clampPercent(undefined)).toBe(0)
  })
})
