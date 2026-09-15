import { expect, test, type Page, type Route } from '@playwright/test'

type WorkflowMockState = {
  analysisGenerated: boolean
  analysisApproved: boolean
  riskGenerated: boolean
  riskApproved: boolean
  scenarioGenerated: boolean
  approvedScenarioIds: string[]
  testCaseGenerated: boolean
  approvedTestCaseIds: string[]
}

type ReviewSelections = {
  scenarios: string[][]
  generatedScenarioIds: string[][]
  testCases: string[][]
}

const project = {
  id: 'project-1',
  project_code: 'EP-VOL-V2',
  name: 'Electronic Pipette Validation',
  description: 'Volume setting vertical slice',
  product_type_id: 'pt-ep',
  knowledge_pack_id: 'kp-ep-1',
  knowledge_pack_version: '1.0',
  status: 'Active',
}

const requirement = {
  id: 'req-1',
  project_id: project.id,
  requirement_code: 'REQ-VOL-001',
  title: 'Set and display aspiration volume',
  original_text:
    'The electronic pipette shall let the operator set 100.0 µL and display the selected volume.',
  requirement_type: 'FUNCTIONAL',
  priority: 'HIGH',
  revision: 1,
  status: 'Active',
  review_status: 'APPROVED',
}

function analysis(state: WorkflowMockState) {
  return {
    id: 'analysis-1',
    requirement_id: requirement.id,
    analysis_version: 1,
    revision: 1,
    summary: 'Operator configures a target aspiration volume',
    intent: 'Validate configuration and presentation of the selected volume.',
    testability: 'TESTABLE',
    assertions: [
      {
        assertion_code: 'AST-001',
        text: 'A selected 100.0 µL value is accepted and displayed.',
      },
    ],
    ambiguities: [],
    missing_information: [],
    questions: [],
    affected_function_ids: ['FN-VOLUME-SETTING'],
    dependencies: [{ type: 'display', name: 'volume display' }],
    knowledge_references: [],
    review_status: state.analysisApproved ? 'APPROVED' : 'AI_DRAFT',
  }
}

function riskBatch(state: WorkflowMockState) {
  const reviewStatus = state.riskApproved ? 'APPROVED' : 'AI_DRAFT'
  return {
    id: 'risk-batch-1',
    version: 1,
    review_status: reviewStatus,
    source_analysis_id: 'analysis-1',
    risks: [
      {
        id: 'risk-1',
        risk_code: 'RISK-VOLUME-001',
        title: 'Displayed volume differs from selected value',
        description: 'The control value and rendered volume can diverge.',
        severity: 'HIGH',
        likelihood: 'MEDIUM',
        priority: 'HIGH',
        rationale: 'A display mismatch can cause an incorrect aspiration operation.',
        requirement_gap: false,
        review_status: reviewStatus,
        revision: 1,
        knowledge_references: [],
      },
    ],
  }
}

function scenarioBatch(state: WorkflowMockState) {
  const definitions = [
    {
      id: 'scenario-nominal',
      scenario_code: 'SCN-VOLUME-NOMINAL',
      title: 'Set a nominal aspiration volume',
      scenario_type: 'NOMINAL',
      expected_behavior_summary: 'The selected 100.0 µL value remains visible.',
      expected_behavior_status: 'DEFINED',
      blocking_questions: [],
    },
    {
      id: 'scenario-min',
      scenario_code: 'SCN-VOLUME-MIN',
      title: 'Set the minimum supported volume',
      scenario_type: 'BOUNDARY',
      expected_behavior_summary: 'The minimum supported volume is accepted.',
      expected_behavior_status: 'DEFINED',
      blocking_questions: [],
    },
    {
      id: 'scenario-max',
      scenario_code: 'SCN-VOLUME-MAX',
      title: 'Set the maximum supported volume',
      scenario_type: 'BOUNDARY',
      expected_behavior_summary: 'The maximum supported volume is accepted.',
      expected_behavior_status: 'DEFINED',
      blocking_questions: [],
    },
    {
      id: 'scenario-below',
      scenario_code: 'SCN-VOLUME-BELOW',
      title: 'Enter a value below the supported minimum',
      scenario_type: 'NEGATIVE',
      expected_behavior_summary: null,
      expected_behavior_status: 'CLARIFICATION_REQUIRED',
      blocking_questions: ['What behavior is required below the supported minimum?'],
    },
    {
      id: 'scenario-persistence',
      scenario_code: 'SCN-VOLUME-PERSISTENCE',
      title: 'Restart after selecting a volume',
      scenario_type: 'PERSISTENCE',
      expected_behavior_summary: null,
      expected_behavior_status: 'CLARIFICATION_REQUIRED',
      blocking_questions: ['Must the selected volume persist after restart?'],
    },
  ]
  const statuses = definitions.map((scenario) =>
    state.approvedScenarioIds.includes(scenario.id) ? 'APPROVED' : 'AI_DRAFT',
  )
  const reviewStatus = statuses.every((status) => status === 'APPROVED')
    ? 'APPROVED'
    : statuses.some((status) => status === 'APPROVED')
      ? 'HUMAN_EDITED'
      : 'AI_DRAFT'
  return {
    id: 'scenario-batch-1',
    version: 1,
    review_status: reviewStatus,
    source_risk_batch_id: 'risk-batch-1',
    scenarios: definitions.map((scenario) => ({
        ...scenario,
        test_intent: 'Verify that a supported value is accepted and displayed unchanged.',
        generation_reason: 'Covers the approved volume/display mismatch risk.',
        priority: 'HIGH',
        mandatory: true,
        review_status: state.approvedScenarioIds.includes(scenario.id) ? 'APPROVED' : 'AI_DRAFT',
        revision: 1,
        knowledge_references: [],
      })),
  }
}

function testCaseBatch(state: WorkflowMockState) {
  const definitions = [
    {
      id: 'testcase-nominal',
      test_case_code: 'TC-VOLUME-NOMINAL',
      title: 'Configure and verify 100.0 µL',
      scenario_id: 'scenario-nominal',
      expected_result_status: 'DEFINED',
      generation_reason: 'Implements the approved nominal volume scenario.',
      configuration: [{ name: 'pipette mode', value: 'aspirate' }],
      test_data: [{ name: 'target volume', value: '100.0 µL' }],
      blocking_questions: [],
      steps: [
        {
          id: 'step-nominal',
          step_no: 1,
          action: 'Set the aspiration volume to 100.0 µL.',
          configuration: { mode: 'aspirate' },
          test_data: { target_volume: '100.0 µL' },
          expected_result: 'The display shows 100.0 µL.',
          expected_result_status: 'DEFINED',
        },
      ],
    },
    {
      id: 'testcase-min',
      test_case_code: 'TC-VOLUME-MIN',
      title: 'Configure the minimum supported volume',
      scenario_id: 'scenario-min',
      expected_result_status: 'DEFINED',
      generation_reason: 'Implements the approved minimum boundary scenario.',
      configuration: [{ name: 'pipette mode', value: 'aspirate' }],
      test_data: [{ name: 'target volume', value: '10.0 µL' }],
      blocking_questions: [],
      steps: [
        {
          id: 'step-min',
          step_no: 1,
          action: 'Set the aspiration volume to 10.0 µL.',
          test_data: { target_volume: '10.0 µL' },
          expected_result: 'The display shows 10.0 µL.',
          expected_result_status: 'DEFINED',
        },
      ],
    },
    {
      id: 'testcase-max',
      test_case_code: 'TC-VOLUME-MAX',
      title: 'Configure the maximum supported volume',
      scenario_id: 'scenario-max',
      expected_result_status: 'DEFINED',
      generation_reason: 'Implements the approved maximum boundary scenario.',
      configuration: [{ name: 'pipette mode', value: 'aspirate' }],
      test_data: [{ name: 'target volume', value: '1000.0 µL' }],
      blocking_questions: [],
      steps: [
        {
          id: 'step-max',
          step_no: 1,
          action: 'Set the aspiration volume to 1000.0 µL.',
          test_data: { target_volume: '1000.0 µL' },
          expected_result: 'The display shows 1000.0 µL.',
          expected_result_status: 'DEFINED',
        },
      ],
    },
    {
      id: 'testcase-persistence',
      test_case_code: 'TC-VOLUME-PERSISTENCE',
      title: 'Restart after selecting 100.0 µL',
      scenario_id: 'scenario-persistence',
      expected_result_status: 'CLARIFICATION_REQUIRED',
      generation_reason: 'Preserves the approved persistence intent without inventing behavior.',
      configuration: [{ name: 'pipette mode', value: 'aspirate' }],
      test_data: [{ name: 'target volume', value: '100.0 µL' }],
      blocking_questions: ['Must the selected volume persist after restart?'],
      steps: [
        {
          id: 'step-persistence',
          step_no: 1,
          action: 'Restart the pipette after selecting 100.0 µL.',
          test_data: { target_volume: '100.0 µL' },
          expected_result: null,
          expected_result_status: 'CLARIFICATION_REQUIRED',
        },
      ],
    },
  ]
  const statuses = definitions.map((testCase) =>
    state.approvedTestCaseIds.includes(testCase.id) ? 'APPROVED' : 'AI_DRAFT',
  )
  return {
    id: 'testcase-batch-1',
    version: 1,
    review_status: statuses.every((status) => status === 'APPROVED')
      ? 'APPROVED'
      : statuses.some((status) => status === 'APPROVED')
        ? 'HUMAN_EDITED'
        : 'AI_DRAFT',
    source_scenario_batch_id: 'scenario-batch-1',
    test_cases: definitions.map((testCase) => ({
        ...testCase,
        priority: 'HIGH',
        review_status: state.approvedTestCaseIds.includes(testCase.id) ? 'APPROVED' : 'AI_DRAFT',
        revision: 1,
        knowledge_references: [],
      })),
  }
}

function workflow(state: WorkflowMockState) {
  let currentStage = 'IMPORTED'
  if (state.analysisGenerated) currentStage = state.analysisApproved ? 'RISK_REVIEW' : 'ANALYSIS_REVIEW'
  if (state.riskGenerated) currentStage = state.riskApproved ? 'SCENARIO_REVIEW' : 'RISK_REVIEW'
  if (state.scenarioGenerated) {
    currentStage = state.approvedScenarioIds.length ? 'TESTCASE_REVIEW' : 'SCENARIO_REVIEW'
  }
  if (state.testCaseGenerated) currentStage = 'TESTCASE_REVIEW'

  const availableActions = ['ANALYZE_REQUIREMENT']
  if (state.analysisGenerated) availableActions.push('REGENERATE_ANALYSIS')
  if (state.analysisGenerated && !state.analysisApproved) availableActions.push('REVIEW_ANALYSIS')
  if (state.analysisApproved) availableActions.push('GENERATE_RISKS')
  if (state.riskGenerated) availableActions.push('REGENERATE_RISKS', 'REVIEW_RISKS')
  if (state.riskApproved) availableActions.push('GENERATE_SCENARIOS')
  if (state.scenarioGenerated) {
    availableActions.push('REGENERATE_SCENARIOS', 'REVIEW_SCENARIOS')
  }
  if (state.approvedScenarioIds.length) availableActions.push('GENERATE_TEST_CASES')
  if (state.testCaseGenerated) {
    availableActions.push('REGENERATE_TEST_CASES', 'REVIEW_TEST_CASES')
  }

  return {
    requirement_id: requirement.id,
    current_stage: currentStage,
    stages: [],
    active_assets: {
      analysis: state.analysisGenerated
        ? {
            type: 'RequirementAnalysis',
            id: 'analysis-1',
            version: 1,
            review_status: state.analysisApproved ? 'APPROVED' : 'AI_DRAFT',
          }
        : null,
      risk_batch: state.riskGenerated
        ? {
            type: 'RiskBatch',
            id: 'risk-batch-1',
            version: 1,
            review_status: state.riskApproved ? 'APPROVED' : 'AI_DRAFT',
          }
        : null,
      scenario_batch: state.scenarioGenerated
        ? {
            type: 'ScenarioBatch',
            id: 'scenario-batch-1',
            version: 1,
            review_status: scenarioBatch(state).review_status,
          }
        : null,
      testcase_batch: state.testCaseGenerated
        ? {
            type: 'TestCaseBatch',
            id: 'testcase-batch-1',
            version: 1,
            review_status: testCaseBatch(state).review_status,
          }
        : null,
    },
    available_actions: availableActions,
    blocking_reasons: [],
  }
}

function succeededRun(id: string, resultType: string, resultId: string) {
  return {
    id,
    task_type: resultType,
    status: 'SUCCEEDED',
    progress: { stage: 'complete', percent: 100 },
    result: { type: resultType, id: resultId },
    error: null,
  }
}

async function installWorkflowApiMock(
  page: Page,
  state: WorkflowMockState,
  unexpected: string[],
  selections: ReviewSelections,
) {
  const runs = new Map<string, ReturnType<typeof succeededRun>>()

  async function json(route: Route, body: unknown, status = 200) {
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  }

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = request.method()

    if (method === 'GET' && path === `/projects/${project.id}`) {
      return json(route, project)
    }
    if (method === 'GET' && path === `/requirements/${requirement.id}`) {
      return json(route, requirement)
    }
    if (method === 'GET' && path === `/requirements/${requirement.id}/workflow`) {
      return json(route, workflow(state))
    }
    if (method === 'POST' && path === `/requirements/${requirement.id}/analyze`) {
      state.analysisGenerated = true
      const run = succeededRun('run-analysis', 'REQUIREMENT_ANALYSIS', 'analysis-1')
      runs.set(run.id, run)
      return json(route, run, 202)
    }
    if (method === 'GET' && path.startsWith('/ai-runs/')) {
      const run = runs.get(path.slice('/ai-runs/'.length))
      return run
        ? json(route, run)
        : json(route, { error: { code: 'NOT_FOUND', message: 'Unknown mocked run' } }, 404)
    }
    if (
      method === 'GET' &&
      path === `/requirements/${requirement.id}/analyses/analysis-1`
    ) {
      return json(route, analysis(state))
    }
    if (
      method === 'PATCH' &&
      path === `/requirements/${requirement.id}/analyses/analysis-1/review`
    ) {
      state.analysisApproved = true
      return json(route, analysis(state))
    }
    if (method === 'POST' && path === '/risks/generate') {
      state.riskGenerated = true
      const run = succeededRun('run-risk', 'RISK_GENERATION', 'risk-batch-1')
      runs.set(run.id, run)
      return json(route, run, 202)
    }
    if (method === 'GET' && path === '/risk-batches/risk-batch-1') {
      return json(route, riskBatch(state))
    }
    if (method === 'POST' && path === '/risk-batches/risk-batch-1/review') {
      state.riskApproved = true
      return json(route, riskBatch(state))
    }
    if (method === 'POST' && path === '/scenarios/generate') {
      state.scenarioGenerated = true
      const run = succeededRun('run-scenario', 'SCENARIO_GENERATION', 'scenario-batch-1')
      runs.set(run.id, run)
      return json(route, run, 202)
    }
    if (method === 'GET' && path === '/scenario-batches/scenario-batch-1') {
      return json(route, scenarioBatch(state))
    }
    if (method === 'POST' && path === '/scenario-batches/scenario-batch-1/review') {
      const payload = request.postDataJSON() as { action: string; scenario_ids: string[] }
      selections.scenarios.push(payload.scenario_ids)
      state.approvedScenarioIds =
        payload.action === 'APPROVE'
          ? [...new Set([...state.approvedScenarioIds, ...payload.scenario_ids])]
          : state.approvedScenarioIds.filter((id) => !payload.scenario_ids.includes(id))
      return json(route, scenarioBatch(state))
    }
    if (method === 'POST' && path === '/testcases/generate') {
      const payload = request.postDataJSON() as { scenario_ids: string[] }
      selections.generatedScenarioIds.push(payload.scenario_ids)
      state.testCaseGenerated = true
      const run = succeededRun('run-testcase', 'TEST_CASE_GENERATION', 'testcase-batch-1')
      runs.set(run.id, run)
      return json(route, run, 202)
    }
    if (method === 'GET' && path === '/testcase-batches/testcase-batch-1') {
      return json(route, testCaseBatch(state))
    }
    if (method === 'POST' && path === '/testcase-batches/testcase-batch-1/review') {
      const payload = request.postDataJSON() as { action: string; test_case_ids: string[] }
      selections.testCases.push(payload.test_case_ids)
      state.approvedTestCaseIds =
        payload.action === 'APPROVE'
          ? [...new Set([...state.approvedTestCaseIds, ...payload.test_case_ids])]
          : state.approvedTestCaseIds.filter((id) => !payload.test_case_ids.includes(id))
      return json(route, testCaseBatch(state))
    }
    if (method === 'GET' && path === `/requirements/${requirement.id}/traceability`) {
      return json(route, {
        nodes: [
          { type: 'Requirement', id: requirement.id, label: requirement.requirement_code },
          { type: 'Assertion', id: 'assertion-1', label: 'AST-001' },
          { type: 'Risk', id: 'risk-1', label: 'RISK-VOLUME-001' },
          { type: 'Scenario', id: 'scenario-nominal', label: 'SCN-VOLUME-NOMINAL' },
          { type: 'TestCase', id: 'testcase-nominal', label: 'TC-VOLUME-NOMINAL' },
        ],
        relations: [
          { source: requirement.id, relation: 'DECOMPOSED_TO', target: 'assertion-1' },
          { source: 'assertion-1', relation: 'EXPOSES', target: 'risk-1' },
          { source: 'risk-1', relation: 'COVERED_BY', target: 'scenario-nominal' },
          { source: 'scenario-nominal', relation: 'IMPLEMENTED_BY', target: 'testcase-nominal' },
        ],
      })
    }

    unexpected.push(`${method} ${path}`)
    return json(
      route,
      { error: { code: 'UNEXPECTED_E2E_REQUEST', message: `${method} ${path}` } },
      500,
    )
  })
}

test('moves a seeded requirement through the human-review gates to traceable test cases', async ({
  page,
}) => {
  const state: WorkflowMockState = {
    analysisGenerated: false,
    analysisApproved: false,
    riskGenerated: false,
    riskApproved: false,
    scenarioGenerated: false,
    approvedScenarioIds: [],
    testCaseGenerated: false,
    approvedTestCaseIds: [],
  }
  const unexpectedRequests: string[] = []
  const selections: ReviewSelections = {
    scenarios: [],
    generatedScenarioIds: [],
    testCases: [],
  }
  await installWorkflowApiMock(page, state, unexpectedRequests, selections)

  await page.goto(`/projects/${project.id}/requirements/${requirement.id}`)
  await expect(page.getByRole('heading', { name: requirement.title })).toBeVisible()
  await expect(page.getByText(requirement.original_text)).toBeVisible()

  await page.getByRole('button', { name: '运行 Requirement Analysis' }).click()
  await expect.poll(() => state.analysisGenerated).toBe(true)

  await page.getByRole('tab', { name: 'Analysis' }).click()
  let panel = page.locator('.ant-tabs-tabpane-active')
  await expect(panel.getByRole('heading', { name: analysis(state).summary })).toBeVisible()
  await expect(panel.getByRole('button', { name: '生成 Risk' })).toBeDisabled()

  await panel.getByRole('button', { name: /批\s*准/ }).click()
  await expect.poll(() => state.analysisApproved).toBe(true)
  await expect(panel.getByText('已批准').first()).toBeVisible()
  await expect(panel.getByRole('button', { name: '生成 Risk' })).toBeEnabled()
  await panel.getByRole('button', { name: '生成 Risk' }).click()
  await expect.poll(() => state.riskGenerated).toBe(true)

  await page.getByRole('tab', { name: 'Risks' }).click()
  panel = page.locator('.ant-tabs-tabpane-active')
  await expect(panel.getByText('Displayed volume differs from selected value')).toBeVisible()
  await expect(panel.getByRole('button', { name: '生成 Scenarios' })).toBeDisabled()

  await panel.getByRole('button', { name: /批\s*准/ }).click()
  await expect.poll(() => state.riskApproved).toBe(true)
  await expect(panel.getByRole('button', { name: '生成 Scenarios' })).toBeEnabled()
  await panel.getByRole('button', { name: '生成 Scenarios' }).click()
  await expect.poll(() => state.scenarioGenerated).toBe(true)

  await page.getByRole('tab', { name: 'Scenarios' }).click()
  panel = page.locator('.ant-tabs-tabpane-active')
  await expect(panel.getByText('Set a nominal aspiration volume')).toBeVisible()
  await expect(panel.getByRole('button', { name: '生成 Test Cases' })).toBeDisabled()

  await panel
    .getByRole('checkbox', { name: '选择 Scenario SCN-VOLUME-BELOW' })
    .uncheck()
  await panel.getByRole('button', { name: /批\s*准/ }).click()
  await expect.poll(() => state.approvedScenarioIds.length).toBe(4)
  expect(selections.scenarios).toEqual([
    [
      'scenario-nominal',
      'scenario-min',
      'scenario-max',
      'scenario-persistence',
    ],
  ])
  await expect(panel.getByRole('button', { name: '生成 Test Cases' })).toBeEnabled()
  await panel.getByRole('button', { name: '生成 Test Cases' }).click()
  await expect.poll(() => state.testCaseGenerated).toBe(true)
  expect(selections.generatedScenarioIds).toEqual([
    [
      'scenario-nominal',
      'scenario-min',
      'scenario-max',
      'scenario-persistence',
    ],
  ])

  await page.getByRole('tab', { name: 'Test Cases' }).click()
  panel = page.locator('.ant-tabs-tabpane-active')
  await expect(panel.getByText('TC-VOLUME-NOMINAL')).toBeVisible()
  await expect(panel.getByText('Configure and verify 100.0 µL')).toBeVisible()
  await expect(panel.getByText('Restart after selecting 100.0 µL')).toBeVisible()
  await expect(panel.getByText('2 个 Expected Result 需要澄清')).toBeVisible()
  await expect(panel.getByText('其中 3 项可批准')).toBeVisible()
  await panel.getByText('Configure and verify 100.0 µL').click()
  await expect(panel.getByText('pipette mode: aspirate')).toBeVisible()
  await expect(panel.getByText('target volume: 100.0 µL')).toBeVisible()
  await expect(panel.getByText('The display shows 100.0 µL.')).toBeVisible()
  await panel.getByRole('button', { name: /批\s*准/ }).click()
  await expect.poll(() => state.approvedTestCaseIds.length).toBe(3)
  expect(selections.testCases).toEqual([
    ['testcase-nominal', 'testcase-min', 'testcase-max'],
  ])
  expect(selections.testCases[0]).not.toContain('testcase-persistence')

  await page.getByRole('tab', { name: 'Traceability' }).click()
  panel = page.locator('.ant-tabs-tabpane-active')
  await expect(
    panel.getByRole('heading', {
      name: 'Requirement → Assertion → Risk → Scenario → Test Case',
    }),
  ).toBeVisible()
  await expect(panel.getByText('TC-VOLUME-NOMINAL')).toBeVisible()
  await expect(panel.getByText('IMPLEMENTED_BY')).toBeVisible()
  expect(unexpectedRequests).toEqual([])
})
