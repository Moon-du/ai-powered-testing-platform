import axios from 'axios'

import {
  normalizeAiRun,
  normalizeAnalysis,
  normalizeCoverage,
  normalizeKnowledgeContext,
  normalizeKnowledgePack,
  normalizeProductType,
  normalizeProject,
  normalizeProjectContext,
  normalizeRequirement,
  normalizeRiskBatch,
  normalizeScenarioBatch,
  normalizeTestCaseBatch,
  normalizeTraceability,
  normalizeWorkflow,
  serializeProjectContext,
} from '@/api/normalize'

import type {
  AiRun,
  CoverageResponse,
  KnowledgeContextSummary,
  KnowledgePack,
  ProductType,
  Project,
  ProjectContextItem,
  ProjectContextResponse,
  Requirement,
  RequirementAnalysis,
  RiskBatch,
  ScenarioBatch,
  TestCaseBatch,
  TraceabilityResponse,
  WorkflowState,
} from '@/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface ApiRequestContext {
  accessToken?: string | null
  userId?: string | null
  actorRole?: string | null
  tenantId?: string | null
}

let requestContextProvider: () => ApiRequestContext = () => ({})

export function configureApiRequestContext(provider: () => ApiRequestContext): void {
  requestContextProvider = provider
}

api.interceptors.request.use((config) => {
  const context = requestContextProvider()
  if (context.accessToken) {
    config.headers.set('Authorization', `Bearer ${context.accessToken}`)
  }

  const useDevHeaders = (import.meta.env.VITE_ENABLE_DEV_HEADERS ?? 'true') === 'true'
  if (useDevHeaders && !context.accessToken) {
    config.headers.set(
      'X-User-Id',
      context.userId ??
        import.meta.env.VITE_DEV_USER_ID ??
        import.meta.env.VITE_DEV_ACTOR_ID ??
        'dev-user',
    )
    config.headers.set(
      'X-Tenant-Id',
      context.tenantId ?? import.meta.env.VITE_DEV_TENANT_ID ?? 'demo-tenant',
    )
  }
  return config
})

export interface Page<T> {
  items: T[]
  total: number
}

function asItems(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: unknown[] }).items
  }
  return []
}

function isNotFound(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 404
}

function newIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function idempotencyConfig(key: string): { headers: { 'Idempotency-Key': string } } {
  return { headers: { 'Idempotency-Key': key } }
}

async function fallbackOn404<T>(primary: () => Promise<T>, fallback: () => Promise<T>): Promise<T> {
  try {
    return await primary()
  } catch (error) {
    if (!isNotFound(error)) throw error
    return fallback()
  }
}

export const platformApi = {
  async listProductTypes(): Promise<ProductType[]> {
    const { data } = await api.get<unknown>('/product-types')
    return asItems(data).map(normalizeProductType)
  },

  async listKnowledgePacks(productTypeId: string): Promise<KnowledgePack[]> {
    const { data } = await api.get<unknown>(
      `/product-types/${productTypeId}/knowledge-packs`,
    )
    return asItems(data).map(normalizeKnowledgePack)
  },

  async listProjects(): Promise<Project[]> {
    const { data } = await api.get<unknown>('/projects')
    return asItems(data).map(normalizeProject)
  },

  async getProject(projectId: string): Promise<Project> {
    const { data } = await api.get<unknown>(`/projects/${projectId}`)
    return normalizeProject(data)
  },

  async getProjectContext(projectId: string): Promise<ProjectContextResponse> {
    const { data } = await api.get<unknown>(`/projects/${projectId}/context`)
    return normalizeProjectContext(data, projectId)
  },

  async updateProjectContext(
    projectId: string,
    items: ProjectContextItem[],
    expectedRevision: number,
  ): Promise<ProjectContextResponse> {
    const { data } = await api.put<unknown>(`/projects/${projectId}/context`, {
      items: serializeProjectContext(items),
      expected_revision: expectedRevision,
    })
    return normalizeProjectContext(data, projectId)
  },

  async getKnowledgeContext(projectId: string): Promise<KnowledgeContextSummary> {
    try {
      const { data } = await api.get<unknown>(`/projects/${projectId}/knowledge-context`)
      return normalizeKnowledgeContext(data)
    } catch (error) {
      if (!isNotFound(error)) throw error
      return normalizeKnowledgeContext({ counts: {} })
    }
  },

  async createProject(input: {
    project_code: string
    name: string
    description?: string
    product_type_id: string
    product_type_code?: string
    knowledge_pack_id: string
    knowledge_pack_version: string
    product_variant?: string
    project_version?: string
  }): Promise<Project> {
    const { data } = await api.post<unknown>('/projects', input)
    return normalizeProject(data)
  },

  async listRequirements(projectId: string): Promise<Requirement[]> {
    const { data } = await api.get<unknown>(`/projects/${projectId}/requirements`)
    return asItems(data).map(normalizeRequirement)
  },

  async createRequirement(
    projectId: string,
    input: Pick<Requirement, 'requirement_code' | 'title' | 'original_text'>,
  ): Promise<Requirement> {
    const { data } = await api.post<unknown>(`/projects/${projectId}/requirements`, input)
    return normalizeRequirement(data)
  },

  async getRequirement(requirementId: string): Promise<Requirement> {
    const { data } = await api.get<unknown>(`/requirements/${requirementId}`)
    return normalizeRequirement(data)
  },

  async getWorkflow(requirementId: string): Promise<WorkflowState> {
    const { data } = await api.get<unknown>(`/requirements/${requirementId}/workflow`)
    return normalizeWorkflow(data, requirementId)
  },

  async analyzeRequirement(requirement: Requirement): Promise<AiRun> {
    const key = newIdempotencyKey()
    const { data } = await api.post<unknown>(`/requirements/${requirement.id}/analyze`, {
      project_id: requirement.project_id,
      requirement_revision: requirement.revision,
      options: {
        strict_grounding: true,
        include_questions: true,
        include_dependency_analysis: true,
        include_testability_analysis: true,
        language: 'zh-CN',
      },
      user_instruction: null,
    }, idempotencyConfig(key))
    return normalizeAiRun(data)
  },

  async getAiRun(runId: string): Promise<AiRun> {
    const { data } = await api.get<unknown>(`/ai-runs/${runId}`)
    return normalizeAiRun(data)
  },

  async getAnalysis(requirementId: string, analysisId: string): Promise<RequirementAnalysis> {
    const data = await fallbackOn404(
      async () => (await api.get<unknown>(`/requirements/${requirementId}/analyses/${analysisId}`)).data,
      async () => (await api.get<unknown>(`/analyses/${analysisId}`)).data,
    )
    return normalizeAnalysis(data)
  },

  async reviewAnalysis(
    requirementId: string,
    analysis: RequirementAnalysis,
    action: 'APPROVE' | 'REJECT',
  ): Promise<RequirementAnalysis> {
    const payload = { action, expected_revision: analysis.revision }
    const data = await fallbackOn404(
      async () =>
        (await api.patch<unknown>(`/requirements/${requirementId}/analyses/${analysis.id}/review`, payload))
          .data,
      async () => (await api.post<unknown>(`/analyses/${analysis.id}/review`, payload)).data,
    )
    return normalizeAnalysis(data)
  },

  async regenerateAnalysis(
    requirementId: string,
    analysis: RequirementAnalysis,
    feedback?: string,
  ): Promise<AiRun> {
    const key = newIdempotencyKey()
    const data = await fallbackOn404(
      async () =>
        (
          await api.post<unknown>(`/requirements/${requirementId}/analyses/${analysis.id}/regenerate`, {
            mode: 'ALL',
            feedback: feedback || null,
            expected_revision: analysis.revision,
            preserve_human_edits: true,
          }, idempotencyConfig(key))
        ).data,
      async () =>
        (await api.post<unknown>(`/requirements/${requirementId}/analyze`, undefined, idempotencyConfig(key)))
          .data,
    )
    return normalizeAiRun(data)
  },

  async generateRisks(requirement: Requirement, analysisId: string): Promise<AiRun> {
    const key = newIdempotencyKey()
    const payload = {
      project_id: requirement.project_id,
      requirement_id: requirement.id,
      analysis_id: analysisId,
      options: {
        include_product_risks: true,
        include_failure_modes: true,
        include_dependency_risks: true,
        include_requirement_gaps: true,
        minimum_priority: 'LOW',
      },
    }
    const data = await fallbackOn404(
      async () => (await api.post<unknown>('/risks/generate', payload, idempotencyConfig(key))).data,
      async () =>
        (await api.post<unknown>(`/analyses/${analysisId}/risks/generate`, { mode: 'ALL', selected_ids: [] }, idempotencyConfig(key)))
          .data,
    )
    return normalizeAiRun(data)
  },

  async getRiskBatch(batchId: string): Promise<RiskBatch> {
    const { data } = await api.get<unknown>(`/risk-batches/${batchId}`)
    return normalizeRiskBatch(data)
  },

  async reviewRiskBatch(batch: RiskBatch, action: 'APPROVE' | 'REJECT'): Promise<RiskBatch> {
    const { data } = await api.post<unknown>(`/risk-batches/${batch.id}/review`, {
      action,
      risk_ids: batch.risks.map((risk) => risk.id),
      expected_revisions: Object.fromEntries(batch.risks.map((risk) => [risk.id, risk.revision])),
    })
    return normalizeRiskBatch(data)
  },

  async regenerateRiskBatch(batch: RiskBatch, feedback?: string): Promise<AiRun> {
    const key = newIdempotencyKey()
    const data = await fallbackOn404(
      async () =>
        (
          await api.post<unknown>(`/risk-batches/${batch.id}/regenerate`, {
            mode: 'ALL',
            feedback: feedback || null,
            preserve_approved_items: true,
          }, idempotencyConfig(key))
        ).data,
      async () => {
        if (!batch.source_analysis_id) throw new Error('Risk Batch 缺少 source_analysis_id，无法重新生成')
        return (
          await api.post<unknown>(`/analyses/${batch.source_analysis_id}/risks/generate`, {
            mode: 'ALL',
            selected_ids: [],
          }, idempotencyConfig(key))
        ).data
      },
    )
    return normalizeAiRun(data)
  },

  async generateScenarios(requirement: Requirement, analysisId: string, riskBatch: RiskBatch): Promise<AiRun> {
    const key = newIdempotencyKey()
    const selectedIds = riskBatch.risks
      .filter((risk) => risk.review_status === 'APPROVED')
      .map((risk) => risk.id)
    const payload = {
      project_id: requirement.project_id,
      requirement_id: requirement.id,
      analysis_id: analysisId,
      risk_batch_id: riskBatch.id,
      risk_selection: selectedIds,
      options: {
        include_nominal: true,
        include_boundary: true,
        include_negative: true,
        include_fault: true,
        include_recovery: true,
        include_persistence: true,
        include_interaction: true,
        include_regression: true,
      },
    }
    const data = await fallbackOn404(
      async () => (await api.post<unknown>('/scenarios/generate', payload, idempotencyConfig(key))).data,
      async () =>
        (
          await api.post<unknown>(`/risk-batches/${riskBatch.id}/scenarios/generate`, {
            mode: 'SELECTED',
            selected_ids: selectedIds,
          }, idempotencyConfig(key))
        ).data,
    )
    return normalizeAiRun(data)
  },

  async getScenarioBatch(batchId: string): Promise<ScenarioBatch> {
    const { data } = await api.get<unknown>(`/scenario-batches/${batchId}`)
    return normalizeScenarioBatch(data)
  },

  async reviewScenarioBatch(
    batch: ScenarioBatch,
    action: 'APPROVE' | 'REJECT',
    scenarioIds: string[],
  ): Promise<ScenarioBatch> {
    const selected = new Set(scenarioIds)
    const { data } = await api.post<unknown>(`/scenario-batches/${batch.id}/review`, {
      action,
      scenario_ids: scenarioIds,
      expected_revisions: Object.fromEntries(
        batch.scenarios
          .filter((scenario) => selected.has(scenario.id))
          .map((scenario) => [scenario.id, scenario.revision]),
      ),
    })
    return normalizeScenarioBatch(data)
  },

  async regenerateScenarioBatch(batch: ScenarioBatch, feedback?: string): Promise<AiRun> {
    const key = newIdempotencyKey()
    const data = await fallbackOn404(
      async () =>
        (
          await api.post<unknown>(`/scenario-batches/${batch.id}/regenerate`, {
            mode: 'ALL',
            feedback: feedback || null,
            preserve_approved_items: true,
          }, idempotencyConfig(key))
        ).data,
      async () => {
        if (!batch.source_risk_batch_id) throw new Error('Scenario Batch 缺少 source_risk_batch_id，无法重新生成')
        return (
          await api.post<unknown>(`/risk-batches/${batch.source_risk_batch_id}/scenarios/generate`, {
            mode: 'ALL',
            selected_ids: [],
          }, idempotencyConfig(key))
        ).data
      },
    )
    return normalizeAiRun(data)
  },

  async generateTestCases(requirement: Requirement, scenarioBatch: ScenarioBatch): Promise<AiRun> {
    const key = newIdempotencyKey()
    const scenarioIds = scenarioBatch.scenarios
      .filter((scenario) => scenario.review_status === 'APPROVED')
      .map((scenario) => scenario.id)
    const payload = {
      project_id: requirement.project_id,
      requirement_id: requirement.id,
      scenario_batch_id: scenarioBatch.id,
      scenario_ids: scenarioIds,
      options: {
        generation_strategy: 'ONE_OR_MORE_PER_SCENARIO',
        step_granularity: 'EXECUTION_READY',
        include_preconditions: true,
        include_configuration: true,
        include_test_data: true,
        expected_result_per_step: true,
        avoid_unspecified_behavior: true,
      },
    }
    const data = await fallbackOn404(
      async () => (await api.post<unknown>('/testcases/generate', payload, idempotencyConfig(key))).data,
      async () =>
        (
          await api.post<unknown>(`/scenario-batches/${scenarioBatch.id}/test-cases/generate`, {
            mode: 'SELECTED',
            selected_ids: scenarioIds,
          }, idempotencyConfig(key))
        ).data,
    )
    return normalizeAiRun(data)
  },

  async getTestCaseBatch(batchId: string): Promise<TestCaseBatch> {
    const data = await fallbackOn404(
      async () => (await api.get<unknown>(`/testcase-batches/${batchId}`)).data,
      async () => (await api.get<unknown>(`/test-case-batches/${batchId}`)).data,
    )
    return normalizeTestCaseBatch(data)
  },

  async reviewTestCaseBatch(
    batch: TestCaseBatch,
    action: 'APPROVE' | 'REJECT',
    testCaseIds: string[],
  ): Promise<TestCaseBatch> {
    const selected = new Set(testCaseIds)
    const payload = {
      action,
      test_case_ids: testCaseIds,
      expected_revisions: Object.fromEntries(
        batch.test_cases
          .filter((testCase) => selected.has(testCase.id))
          .map((testCase) => [testCase.id, testCase.revision]),
      ),
    }
    const data = await fallbackOn404(
      async () => (await api.post<unknown>(`/testcase-batches/${batch.id}/review`, payload)).data,
      async () => (await api.post<unknown>(`/test-case-batches/${batch.id}/review`, payload)).data,
    )
    return normalizeTestCaseBatch(data)
  },

  async regenerateTestCaseBatch(batch: TestCaseBatch, feedback?: string): Promise<AiRun> {
    const key = newIdempotencyKey()
    const data = await fallbackOn404(
      async () =>
        (
          await api.post<unknown>(`/testcase-batches/${batch.id}/regenerate`, {
            mode: 'ALL',
            feedback: feedback || null,
            preserve_approved_items: true,
          }, idempotencyConfig(key))
        ).data,
      async () => {
        if (!batch.source_scenario_batch_id) {
          throw new Error('Test Case Batch 缺少 source_scenario_batch_id，无法重新生成')
        }
        return (
          await api.post<unknown>(
            `/scenario-batches/${batch.source_scenario_batch_id}/test-cases/generate`,
            { mode: 'ALL', selected_ids: [] },
            idempotencyConfig(key),
          )
        ).data
      },
    )
    return normalizeAiRun(data)
  },

  async getTraceability(requirementId: string, projectId?: string): Promise<TraceabilityResponse> {
    const data = await fallbackOn404(
      async () => (await api.get<unknown>(`/requirements/${requirementId}/traceability`)).data,
      async () => {
        if (!projectId) throw new Error('缺少 projectId，无法加载项目级 Traceability')
        return (await api.get<unknown>(`/projects/${projectId}/traceability`)).data
      },
    )
    return normalizeTraceability(data)
  },

  async getCoverage(projectId: string): Promise<CoverageResponse> {
    const { data } = await api.get<unknown>(`/projects/${projectId}/coverage`)
    return normalizeCoverage(data)
  },
}

export function readableApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.error
    if (detail?.message) return detail.message
    if (typeof error.response?.data?.detail === 'string') return error.response.data.detail
    return error.message
  }
  return error instanceof Error ? error.message : '未知错误'
}
