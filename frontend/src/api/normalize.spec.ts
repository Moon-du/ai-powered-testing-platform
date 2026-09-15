import {
  normalizeAiRun,
  normalizeCoverage,
  normalizeKnowledgeContext,
  normalizeScenarioBatch,
  normalizeTestCaseBatch,
  normalizeWorkflow,
} from '@/api/normalize'

describe('API compatibility normalizers', () => {
  it('maps ORM run and scenario batch fields to the PRD UI model', () => {
    const run = normalizeAiRun({
      id: 'run-1',
      run_type: 'SCENARIO',
      status: 'SUCCEEDED',
      result_type: 'SCENARIO_BATCH',
      result_id: 'sb-1',
    })
    const batch = normalizeScenarioBatch({
      id: 'sb-1',
      revision: 2,
      status: 'AI_DRAFT',
      source_risk_batch_id: 'rb-1',
      items: [
        {
          id: 'scenario-1',
          code: 'SC-001',
          title: 'Below minimum',
          intent: 'Verify lower-bound handling',
          category: 'NEGATIVE',
          expected_result: null,
          expected_result_status: 'CLARIFICATION_REQUIRED',
          blocking_questions_json: ['What behavior is expected?'],
          why_generated: 'Boundary risk',
          status: 'AI_DRAFT',
          asset_revision: 3,
        },
      ],
    })

    expect(run.task_type).toBe('SCENARIO')
    expect(run.result).toEqual({ type: 'SCENARIO_BATCH', id: 'sb-1' })
    expect(batch.scenarios[0]?.scenario_code).toBe('SC-001')
    expect(batch.scenarios[0]?.test_intent).toBe('Verify lower-bound handling')
    expect(batch.scenarios[0]?.blocking_questions).toEqual(['What behavior is expected?'])
    expect(batch.scenarios[0]?.revision).toBe(3)
  })

  it('infers workflow stage and normalizes backend coverage names', () => {
    const workflow = normalizeWorkflow(
      {
        active_assets: {
          analysis: { id: 'ra-1', status: 'APPROVED', revision: 2 },
          risk_batch: { id: 'rb-1', status: 'AI_DRAFT', revision: 1 },
        },
        blockers: [],
      },
      'req-1',
    )
    const coverage = normalizeCoverage({
      requirements: { total: 5, analyzed: 4, approved: 3 },
      assertions: { covered: 8, total: 10, percent: 80 },
      risks: { covered: 6, total: 8, percent: 75 },
      scenarios: { approved: 7, total: 9 },
      cases: { approved: 12, total: 15 },
      issues: { requirement_gaps: 2, clarification_required: 1, stale_assets: 3 },
    })

    expect(workflow.current_stage).toBe('RISK_REVIEW')
    expect(coverage.assertion_coverage.percentage).toBe(80)
    expect(coverage.test_cases.approved).toBe(12)
    expect(coverage.issues.undefined_expected_behaviors).toBe(1)
  })

  it('maps backend knowledge-pack metadata and item counts', () => {
    const context = normalizeKnowledgeContext({
      knowledge_pack: { id: 'pack-1', version: '1.0' },
      item_counts: { PRODUCT_FUNCTION: 3, TESTING_RULE: 2 },
      items: [],
    })

    expect(context.knowledge_pack_id).toBe('pack-1')
    expect(context.knowledge_pack_version).toBe('1.0')
    expect(context.counts).toEqual({ PRODUCT_FUNCTION: 3, TESTING_RULE: 2 })
  })

  it('preserves structured case configuration and step test data', () => {
    const batch = normalizeTestCaseBatch({
      id: 'tcb-1',
      revision: 1,
      status: 'AI_DRAFT',
      source_scenario_batch_id: 'sb-1',
      items: [
        {
          id: 'tc-1',
          code: 'TC-001',
          title: 'Nominal volume',
          objective: 'Verify a supported volume',
          scenario_id: 'scenario-1',
          preconditions_json: ['Pipette is idle'],
          configuration_json: { mode: 'aspirate', unit: 'µL' },
          expected_result: '100.0 µL is displayed',
          expected_result_status: 'DEFINED',
          status: 'AI_DRAFT',
          asset_revision: 1,
          steps: [
            {
              id: 'step-1',
              sequence: 1,
              action: 'Set the volume',
              test_data: { target_volume: '100.0 µL' },
              expected_result: '100.0 µL is displayed',
            },
          ],
        },
      ],
    })

    expect(batch.test_cases[0]?.configuration).toEqual({ mode: 'aspirate', unit: 'µL' })
    expect(batch.test_cases[0]?.preconditions).toEqual(['Pipette is idle'])
    expect(batch.test_cases[0]?.steps[0]?.test_data).toEqual({ target_volume: '100.0 µL' })
  })
})
