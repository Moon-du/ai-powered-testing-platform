<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  ArrowLeftOutlined,
  BranchesOutlined,
  BulbOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import { platformApi, readableApiError } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import AiGenerationStatus from '@/components/workflow/AiGenerationStatus.vue'
import KnowledgeReferenceList from '@/components/workflow/KnowledgeReferenceList.vue'
import ReviewActions from '@/components/workflow/ReviewActions.vue'
import WhyGeneratedDrawer from '@/components/workflow/WhyGeneratedDrawer.vue'
import type {
  AiRun,
  KnowledgeReference,
  RequirementAnalysis,
  RequirementRisk,
  RiskBatch,
  ScenarioBatch,
  TestCase,
  TestCaseBatch,
  TestScenario,
  WorkflowAction,
} from '@/types'
import { recordText } from '@/utils/presentation'
import {
  activeAssetId,
  approvableTestCaseIds,
  canInvokeWorkflowAction,
  canGenerateTestCases,
  countClarificationRequired,
} from '@/utils/workflow'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const projectId = String(route.params.projectId)
const requirementId = String(route.params.requirementId)
const activeTab = ref('requirement')
const busyAction = ref<string | null>(null)
const activeRunId = ref<string | null>(null)
const latestRun = ref<AiRun | null>(null)
const handledRuns = new Set<string>()

const whyOpen = ref(false)
const whyTitle = ref('为什么生成')
const whyReason = ref('')
const whyReferences = ref<KnowledgeReference[]>([])
const whyTrace = ref<string[]>([])

const projectQuery = useQuery({
  queryKey: ['project', projectId],
  queryFn: () => platformApi.getProject(projectId),
})
const requirementQuery = useQuery({
  queryKey: ['requirement', requirementId],
  queryFn: () => platformApi.getRequirement(requirementId),
})
const workflowQuery = useQuery({
  queryKey: ['workflow', requirementId],
  queryFn: () => platformApi.getWorkflow(requirementId),
  refetchInterval: 10_000,
})

const analysisId = computed(() => activeAssetId(workflowQuery.data.value, 'analysis'))
const riskBatchId = computed(() => activeAssetId(workflowQuery.data.value, 'riskBatch'))
const scenarioBatchId = computed(() => activeAssetId(workflowQuery.data.value, 'scenarioBatch'))
const testCaseBatchId = computed(() => activeAssetId(workflowQuery.data.value, 'testCaseBatch'))

const analysisQuery = useQuery({
  queryKey: computed(() => ['analysis', requirementId, analysisId.value]),
  queryFn: () => platformApi.getAnalysis(requirementId, analysisId.value as string),
  enabled: computed(() => Boolean(analysisId.value)),
})
const riskBatchQuery = useQuery({
  queryKey: computed(() => ['risk-batch', riskBatchId.value]),
  queryFn: () => platformApi.getRiskBatch(riskBatchId.value as string),
  enabled: computed(() => Boolean(riskBatchId.value)),
})
const scenarioBatchQuery = useQuery({
  queryKey: computed(() => ['scenario-batch', scenarioBatchId.value]),
  queryFn: () => platformApi.getScenarioBatch(scenarioBatchId.value as string),
  enabled: computed(() => Boolean(scenarioBatchId.value)),
})
const testCaseBatchQuery = useQuery({
  queryKey: computed(() => ['testcase-batch', testCaseBatchId.value]),
  queryFn: () => platformApi.getTestCaseBatch(testCaseBatchId.value as string),
  enabled: computed(() => Boolean(testCaseBatchId.value)),
})
const traceabilityQuery = useQuery({
  queryKey: ['traceability', requirementId],
  queryFn: () => platformApi.getTraceability(requirementId, projectId),
  enabled: computed(() => activeTab.value === 'traceability'),
})

const aiRunQuery = useQuery({
  queryKey: computed(() => ['ai-run', activeRunId.value]),
  queryFn: () => platformApi.getAiRun(activeRunId.value as string),
  enabled: computed(() => Boolean(activeRunId.value)),
  refetchInterval: 1_500,
})

const visibleRun = computed(() => aiRunQuery.data.value ?? latestRun.value)
const generationInFlight = computed(
  () => Boolean(activeRunId.value) || busyAction.value !== null,
)
const workflowSteps = [
  { key: 'IMPORTED', title: 'Requirement' },
  { key: 'ANALYSIS_REVIEW', title: 'Analysis' },
  { key: 'RISK_REVIEW', title: 'Risk' },
  { key: 'SCENARIO_REVIEW', title: 'Scenario' },
  { key: 'TESTCASE_REVIEW', title: 'Test Case' },
  { key: 'READY', title: 'Ready' },
]
const currentStep = computed(() => {
  const stage = workflowQuery.data.value?.current_stage
  if (stage === 'ANALYZING') return 0
  const index = workflowSteps.findIndex((item) => item.key === stage)
  return index < 0 ? 0 : index
})
const approvedRisks = computed(
  () => riskBatchQuery.data.value?.risks.filter((risk) => risk.review_status === 'APPROVED') ?? [],
)
const approvedScenarios = computed(
  () => scenarioBatchQuery.data.value?.scenarios.filter((scenario) => scenario.review_status === 'APPROVED') ?? [],
)
const clarificationCount = computed(() =>
  countClarificationRequired(testCaseBatchQuery.data.value?.test_cases ?? []),
)
const selectedScenarioIds = ref<string[]>([])
const selectedTestCaseIds = ref<string[]>([])
const reviewableScenarios = computed(
  () =>
    scenarioBatchQuery.data.value?.scenarios.filter(
      (scenario) => !['APPROVED', 'STALE', 'SUPERSEDED'].includes(scenario.review_status),
    ) ?? [],
)
const reviewableTestCases = computed(
  () =>
    testCaseBatchQuery.data.value?.test_cases.filter(
      (testCase) => !['APPROVED', 'STALE', 'SUPERSEDED'].includes(testCase.review_status),
    ) ?? [],
)
const selectedApprovableTestCaseIds = computed(() =>
  approvableTestCaseIds(
    testCaseBatchQuery.data.value?.test_cases ?? [],
    selectedTestCaseIds.value,
  ),
)
const selectedBlockedTestCaseCount = computed(
  () => selectedTestCaseIds.value.length - selectedApprovableTestCaseIds.value.length,
)

watch(
  () => reviewableScenarios.value.map((scenario) => `${scenario.id}:${scenario.revision}`).join('|'),
  () => {
    const eligible = reviewableScenarios.value.map((scenario) => scenario.id)
    const eligibleSet = new Set(eligible)
    const preserved = selectedScenarioIds.value.filter((id) => eligibleSet.has(id))
    selectedScenarioIds.value = preserved.length ? preserved : eligible
  },
  { immediate: true },
)

watch(
  () => reviewableTestCases.value.map((testCase) => `${testCase.id}:${testCase.revision}`).join('|'),
  () => {
    const eligible = reviewableTestCases.value.map((testCase) => testCase.id)
    const eligibleSet = new Set(eligible)
    const preserved = selectedTestCaseIds.value.filter((id) => eligibleSet.has(id))
    selectedTestCaseIds.value = preserved.length ? preserved : eligible
  },
  { immediate: true },
)

watch(
  () => aiRunQuery.data.value,
  async (run) => {
    if (!run) return
    latestRun.value = run
    if ((run.status === 'SUCCEEDED' || run.status === 'FAILED') && !handledRuns.has(run.id)) {
      handledRuns.add(run.id)
      activeRunId.value = null
      if (run.status === 'SUCCEEDED') {
        await refreshAll()
        void message.success('生成完成，工作流已刷新')
      }
    }
  },
)

async function refreshAll(): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['workflow', requirementId] }),
    queryClient.invalidateQueries({ queryKey: ['requirement', requirementId] }),
    queryClient.invalidateQueries({ queryKey: ['coverage', projectId] }),
    queryClient.invalidateQueries({ queryKey: ['traceability', requirementId] }),
  ])
}

async function startRun(label: string, action: () => Promise<AiRun>): Promise<void> {
  if (generationInFlight.value) return
  busyAction.value = label
  try {
    const run = await action()
    latestRun.value = run
    activeRunId.value = run.id
  } catch (error) {
    void message.error(readableApiError(error))
  } finally {
    busyAction.value = null
  }
}

function actionAvailable(action: WorkflowAction): boolean {
  return canInvokeWorkflowAction(
    workflowQuery.data.value,
    action,
    generationInFlight.value,
  )
}

function checkboxChecked(event: unknown): boolean {
  return Boolean((event as { target?: { checked?: boolean } })?.target?.checked)
}

function toggleScenarioSelection(id: string, checked: boolean): void {
  selectedScenarioIds.value = checked
    ? [...new Set([...selectedScenarioIds.value, id])]
    : selectedScenarioIds.value.filter((selectedId) => selectedId !== id)
}

function toggleTestCaseSelection(id: string, checked: boolean): void {
  selectedTestCaseIds.value = checked
    ? [...new Set([...selectedTestCaseIds.value, id])]
    : selectedTestCaseIds.value.filter((selectedId) => selectedId !== id)
}

function runRequirementAnalysis(): void {
  if (!actionAvailable('ANALYZE_REQUIREMENT')) return
  const requirement = requirementQuery.data.value
  if (requirement) void startRun('analyze', () => platformApi.analyzeRequirement(requirement))
}

function regenerateAnalysis(): void {
  if (!actionAvailable('REGENERATE_ANALYSIS')) return
  const analysis = analysisQuery.data.value
  if (analysis) {
    void startRun('analysis-regenerate', () =>
      platformApi.regenerateAnalysis(requirementId, analysis),
    )
  }
}

function runRiskGeneration(): void {
  if (!actionAvailable('GENERATE_RISKS')) return
  const requirement = requirementQuery.data.value
  const analysis = analysisQuery.data.value
  if (requirement && analysis) {
    void startRun('risk-generate', () => platformApi.generateRisks(requirement, analysis.id))
  }
}

function regenerateRisks(): void {
  if (!actionAvailable('REGENERATE_RISKS')) return
  const batch = riskBatchQuery.data.value
  if (batch) void startRun('risk-regenerate', () => platformApi.regenerateRiskBatch(batch))
}

function runScenarioGeneration(): void {
  if (!actionAvailable('GENERATE_SCENARIOS')) return
  const requirement = requirementQuery.data.value
  const analysis = analysisQuery.data.value
  const batch = riskBatchQuery.data.value
  if (requirement && analysis && batch) {
    void startRun('scenario-generate', () =>
      platformApi.generateScenarios(requirement, analysis.id, batch),
    )
  }
}

function regenerateScenarios(): void {
  if (!actionAvailable('REGENERATE_SCENARIOS')) return
  const batch = scenarioBatchQuery.data.value
  if (batch) {
    void startRun('scenario-regenerate', () => platformApi.regenerateScenarioBatch(batch))
  }
}

function runTestCaseGeneration(): void {
  if (!actionAvailable('GENERATE_TEST_CASES')) return
  const requirement = requirementQuery.data.value
  const batch = scenarioBatchQuery.data.value
  if (requirement && batch) {
    void startRun('testcase-generate', () => platformApi.generateTestCases(requirement, batch))
  }
}

function regenerateTestCases(): void {
  if (!actionAvailable('REGENERATE_TEST_CASES')) return
  const batch = testCaseBatchQuery.data.value
  if (batch) {
    void startRun('testcase-regenerate', () => platformApi.regenerateTestCaseBatch(batch))
  }
}

async function reviewAnalysis(action: 'APPROVE' | 'REJECT'): Promise<void> {
  if (!actionAvailable('REVIEW_ANALYSIS')) return
  const analysis = analysisQuery.data.value
  if (!analysis) return
  busyAction.value = 'analysis-review'
  try {
    const updated = await platformApi.reviewAnalysis(requirementId, analysis, action)
    queryClient.setQueryData<RequirementAnalysis>(['analysis', requirementId, analysis.id], updated)
    await refreshAll()
    void message.success(action === 'APPROVE' ? 'Analysis 已批准' : 'Analysis 已拒绝')
  } catch (error) {
    void message.error(readableApiError(error))
  } finally {
    busyAction.value = null
  }
}

async function reviewRisks(action: 'APPROVE' | 'REJECT'): Promise<void> {
  if (!actionAvailable('REVIEW_RISKS')) return
  const batch = riskBatchQuery.data.value
  if (!batch) return
  busyAction.value = 'risk-review'
  try {
    const updated = await platformApi.reviewRiskBatch(batch, action)
    queryClient.setQueryData<RiskBatch>(['risk-batch', batch.id], updated)
    await refreshAll()
    void message.success(action === 'APPROVE' ? 'Risk Batch 已批准' : 'Risk Batch 已拒绝')
  } catch (error) {
    void message.error(readableApiError(error))
  } finally {
    busyAction.value = null
  }
}

async function reviewScenarios(action: 'APPROVE' | 'REJECT'): Promise<void> {
  if (!actionAvailable('REVIEW_SCENARIOS')) return
  const batch = scenarioBatchQuery.data.value
  if (!batch) return
  const scenarioIds = selectedScenarioIds.value
  if (!scenarioIds.length) {
    void message.warning('请至少选择一个 Scenario')
    return
  }
  busyAction.value = 'scenario-review'
  try {
    const updated = await platformApi.reviewScenarioBatch(batch, action, scenarioIds)
    queryClient.setQueryData<ScenarioBatch>(['scenario-batch', batch.id], updated)
    await refreshAll()
    void message.success(action === 'APPROVE' ? 'Scenario 已批准，可以生成 Test Case' : 'Scenario 已拒绝')
  } catch (error) {
    void message.error(readableApiError(error))
  } finally {
    busyAction.value = null
  }
}

async function reviewTestCases(action: 'APPROVE' | 'REJECT'): Promise<void> {
  if (!actionAvailable('REVIEW_TEST_CASES')) return
  const batch = testCaseBatchQuery.data.value
  if (!batch) return
  const testCaseIds =
    action === 'APPROVE'
      ? selectedApprovableTestCaseIds.value
      : selectedTestCaseIds.value
  if (!testCaseIds.length) {
    void message.warning(
      action === 'APPROVE'
        ? '所选用例没有可批准的执行就绪项'
        : '请至少选择一个 Test Case',
    )
    return
  }
  busyAction.value = 'testcase-review'
  try {
    const updated = await platformApi.reviewTestCaseBatch(batch, action, testCaseIds)
    queryClient.setQueryData<TestCaseBatch>(['testcase-batch', batch.id], updated)
    await refreshAll()
    void message.success(action === 'APPROVE' ? 'Test Case 已批准' : 'Test Case 已拒绝')
  } catch (error) {
    void message.error(readableApiError(error))
  } finally {
    busyAction.value = null
  }
}

function showWhy(
  title: string,
  reason: string,
  references: KnowledgeReference[] | undefined,
  trace: string[],
): void {
  whyTitle.value = title
  whyReason.value = reason
  whyReferences.value = references ?? []
  whyTrace.value = trace
  whyOpen.value = true
}

function showRiskWhy(risk: RequirementRisk): void {
  showWhy(
    `${risk.risk_code} · 为什么识别此风险`,
    risk.rationale,
    risk.knowledge_references,
    [requirementQuery.data.value?.requirement_code ?? requirementId, risk.risk_code],
  )
}

function showScenarioWhy(scenario: TestScenario): void {
  showWhy(
    `${scenario.scenario_code} · 为什么生成此场景`,
    scenario.generation_reason,
    scenario.knowledge_references,
    [requirementQuery.data.value?.requirement_code ?? requirementId, 'Requirement Risk', scenario.scenario_code],
  )
}

function showTestCaseWhy(testCase: TestCase): void {
  showWhy(
    `${testCase.test_case_code} · 为什么生成此用例`,
    testCase.generation_reason ?? `Generated from approved scenario ${testCase.scenario_id}`,
    testCase.knowledge_references,
    [requirementQuery.data.value?.requirement_code ?? requirementId, testCase.scenario_id, testCase.test_case_code],
  )
}
</script>

<template>
  <PageHeader
    eyebrow="Requirement Workflow Workspace"
    :title="requirementQuery.data.value?.title || requirementQuery.data.value?.requirement_code || '需求工作台'"
    :subtitle="projectQuery.data.value ? `${projectQuery.data.value.name} · ${requirementQuery.data.value?.requirement_code ?? ''}` : '结构化分析、风险、场景、用例与追溯。'"
  >
    <template #actions>
      <a-button @click="void router.push({ name: 'project-requirements', params: { projectId } })">
        <template #icon><ArrowLeftOutlined /></template>
        返回需求列表
      </a-button>
      <StatusTag :status="workflowQuery.data.value?.current_stage" kind="workflow" />
    </template>
  </PageHeader>

  <AiGenerationStatus :run="visibleRun" />

  <a-card class="surface-card workflow-header" :bordered="false">
    <a-steps :current="currentStep" responsive>
      <a-step v-for="step in workflowSteps" :key="step.key" :title="step.title" />
    </a-steps>
    <a-alert
      v-if="workflowQuery.data.value?.current_stage === 'STALE'"
      type="warning"
      show-icon
      message="上游测试语义已变化，下游资产标记为 STALE。"
      description="请从最早受影响阶段重新审阅或生成；旧版本仍保留用于追溯。"
      style="margin-top: 18px"
    />
    <a-alert
      v-for="reason in workflowQuery.data.value?.blocking_reasons ?? []"
      :key="reason.code"
      type="error"
      show-icon
      :message="reason.message"
      :description="reason.code"
      style="margin-top: 12px"
    />
  </a-card>

  <a-tabs v-model:active-key="activeTab" class="workspace-tabs" style="margin-top: 22px">
    <a-tab-pane key="requirement" tab="Requirement">
      <a-card class="surface-card" :bordered="false">
        <a-skeleton v-if="requirementQuery.isPending.value" active />
        <ErrorState
          v-else-if="requirementQuery.isError.value"
          :message="readableApiError(requirementQuery.error.value)"
          @retry="void requirementQuery.refetch()"
        />
        <template v-else-if="requirementQuery.data.value">
          <div class="inline-actions">
            <a-space wrap>
              <StatusTag :status="requirementQuery.data.value.review_status" kind="review" />
              <a-tag>Revision {{ requirementQuery.data.value.revision }}</a-tag>
              <a-tag v-if="requirementQuery.data.value.requirement_type" color="purple">{{ requirementQuery.data.value.requirement_type }}</a-tag>
            </a-space>
            <a-button
              type="primary"
              :loading="busyAction === 'analyze'"
              :disabled="!actionAvailable('ANALYZE_REQUIREMENT')"
              @click="runRequirementAnalysis"
            >
              <template #icon><PlayCircleOutlined /></template>
              {{ analysisId ? '重新运行 Analysis' : '运行 Requirement Analysis' }}
            </a-button>
          </div>
          <a-divider />
          <a-typography-title :level="5">Original Text</a-typography-title>
          <a-typography-paragraph class="requirement-text">
            {{ requirementQuery.data.value.original_text }}
          </a-typography-paragraph>
          <a-alert
            message="Requirement 原文是业务事实"
            description="AI 只创建独立的 Analysis 与 Questions，不会覆盖或静默补全原文。"
            type="info"
            show-icon
          />
        </template>
      </a-card>
    </a-tab-pane>

    <a-tab-pane key="analysis" tab="Analysis">
      <a-card class="surface-card" :bordered="false">
        <a-skeleton v-if="analysisQuery.isPending.value && analysisId" active />
        <ErrorState
          v-else-if="analysisQuery.isError.value"
          :message="readableApiError(analysisQuery.error.value)"
          @retry="void analysisQuery.refetch()"
        />
        <a-empty v-else-if="!analysisQuery.data.value" description="尚未生成 Requirement Analysis">
          <a-button
            v-if="requirementQuery.data.value"
            type="primary"
            :disabled="!actionAvailable('ANALYZE_REQUIREMENT')"
            @click="runRequirementAnalysis"
          >
            生成 Analysis
          </a-button>
        </a-empty>
        <template v-else>
          <div class="inline-actions">
            <a-space wrap>
              <StatusTag :status="analysisQuery.data.value.review_status" kind="review" />
              <a-tag>Version {{ analysisQuery.data.value.analysis_version }}</a-tag>
              <a-tag v-if="analysisQuery.data.value.testability" color="cyan">{{ analysisQuery.data.value.testability }}</a-tag>
            </a-space>
            <ReviewActions
              :status="analysisQuery.data.value.review_status"
              :loading="busyAction === 'analysis-review'"
              :review-disabled="!actionAvailable('REVIEW_ANALYSIS')"
              :regenerate-disabled="!actionAvailable('REGENERATE_ANALYSIS')"
              @approve="void reviewAnalysis('APPROVE')"
              @reject="void reviewAnalysis('REJECT')"
              @regenerate="regenerateAnalysis"
            />
          </div>

          <a-divider />
          <a-typography-title :level="4">{{ analysisQuery.data.value.summary }}</a-typography-title>
          <a-typography-paragraph v-if="analysisQuery.data.value.intent">{{ analysisQuery.data.value.intent }}</a-typography-paragraph>

          <a-row :gutter="[18, 18]">
            <a-col :xs="24" :lg="14">
              <a-card title="Atomic Assertions" size="small" class="asset-card">
                <a-list :data-source="analysisQuery.data.value.assertions ?? []" size="small">
                  <template #renderItem="{ item, index }">
                    <a-list-item><a-tag>A{{ String(index + 1).padStart(2, '0') }}</a-tag>{{ recordText(item) }}</a-list-item>
                  </template>
                </a-list>
                <a-empty v-if="!(analysisQuery.data.value.assertions?.length)" description="暂无 Assertion" :image="null" />
              </a-card>
            </a-col>
            <a-col :xs="24" :lg="10">
              <a-card title="Function & Dependency" size="small" class="asset-card">
                <a-descriptions :column="1" size="small">
                  <a-descriptions-item label="Primary Function">{{ analysisQuery.data.value.primary_function_id || '未映射' }}</a-descriptions-item>
                  <a-descriptions-item label="Affected Functions">{{ analysisQuery.data.value.affected_function_ids?.join(', ') || '未提供' }}</a-descriptions-item>
                  <a-descriptions-item label="Dependencies">{{ analysisQuery.data.value.dependencies?.map((item) => recordText(item)).join('；') || '未提供' }}</a-descriptions-item>
                </a-descriptions>
              </a-card>
            </a-col>
          </a-row>

          <a-row :gutter="[18, 18]" style="margin-top: 18px">
            <a-col :xs="24" :lg="8">
              <a-card title="Ambiguities" size="small" class="asset-card asset-card--gap">
                <a-list :data-source="analysisQuery.data.value.ambiguities ?? []" size="small">
                  <template #renderItem="{ item }"><a-list-item>{{ recordText(item) }}</a-list-item></template>
                </a-list>
                <span v-if="!(analysisQuery.data.value.ambiguities?.length)" class="muted">未发现歧义</span>
              </a-card>
            </a-col>
            <a-col :xs="24" :lg="8">
              <a-card title="Missing Information" size="small" class="asset-card asset-card--gap">
                <a-list :data-source="analysisQuery.data.value.missing_information ?? []" size="small">
                  <template #renderItem="{ item }"><a-list-item>{{ recordText(item) }}</a-list-item></template>
                </a-list>
                <span v-if="!(analysisQuery.data.value.missing_information?.length)" class="muted">未发现缺失信息</span>
              </a-card>
            </a-col>
            <a-col :xs="24" :lg="8">
              <a-card title="Questions" size="small" class="asset-card asset-card--gap">
                <a-list :data-source="analysisQuery.data.value.questions ?? []" size="small">
                  <template #renderItem="{ item }"><a-list-item>{{ recordText(item) }}</a-list-item></template>
                </a-list>
                <span v-if="!(analysisQuery.data.value.questions?.length)" class="muted">暂无待澄清问题</span>
              </a-card>
            </a-col>
          </a-row>

          <a-divider />
          <a-collapse ghost>
            <a-collapse-panel key="knowledge" header="查看 Knowledge References">
              <KnowledgeReferenceList :references="analysisQuery.data.value.knowledge_references" />
            </a-collapse-panel>
          </a-collapse>

          <div style="margin-top: 20px; text-align: right">
            <a-tooltip :title="analysisQuery.data.value.review_status === 'APPROVED' ? '' : '先批准 Analysis'">
              <a-button
                type="primary"
                :disabled="!actionAvailable('GENERATE_RISKS') || analysisQuery.data.value.review_status !== 'APPROVED' || !requirementQuery.data.value"
                @click="runRiskGeneration"
              >
                生成 Risk
              </a-button>
            </a-tooltip>
          </div>
        </template>
      </a-card>
    </a-tab-pane>

    <a-tab-pane key="risks" tab="Risks">
      <a-card class="surface-card" :bordered="false">
        <a-skeleton v-if="riskBatchQuery.isPending.value && riskBatchId" active />
        <ErrorState
          v-else-if="riskBatchQuery.isError.value"
          :message="readableApiError(riskBatchQuery.error.value)"
          @retry="void riskBatchQuery.refetch()"
        />
        <a-empty v-else-if="!riskBatchQuery.data.value" description="尚未生成 Requirement Risks">
          <a-button
            v-if="requirementQuery.data.value"
            type="primary"
            :disabled="!actionAvailable('GENERATE_RISKS') || analysisQuery.data.value?.review_status !== 'APPROVED'"
            @click="runRiskGeneration"
          >
            生成 Risks
          </a-button>
        </a-empty>
        <template v-else>
          <div class="inline-actions">
            <div>
              <h2 class="section-title">Requirement-specific Risks</h2>
              <span class="muted">Batch v{{ riskBatchQuery.data.value.version }} · {{ riskBatchQuery.data.value.risks.length }} 项</span>
            </div>
            <ReviewActions
              :status="riskBatchQuery.data.value.review_status"
              :loading="busyAction === 'risk-review'"
              :review-disabled="!actionAvailable('REVIEW_RISKS')"
              :regenerate-disabled="!actionAvailable('REGENERATE_RISKS')"
              @approve="void reviewRisks('APPROVE')"
              @reject="void reviewRisks('REJECT')"
              @regenerate="regenerateRisks"
            />
          </div>
          <a-divider />
          <div class="asset-list">
            <a-card
              v-for="risk in riskBatchQuery.data.value.risks"
              :key="risk.id"
              size="small"
              class="asset-card"
              :class="{ 'asset-card--gap': risk.requirement_gap }"
            >
              <template #title>
                <a-space wrap>
                  <span class="mono">{{ risk.risk_code }}</span>
                  <span>{{ risk.title }}</span>
                </a-space>
              </template>
              <template #extra><StatusTag :status="risk.review_status" kind="review" /></template>
              <a-space wrap style="margin-bottom: 10px">
                <a-tag v-if="risk.priority" color="red">{{ risk.priority }} Priority</a-tag>
                <a-tag v-if="risk.severity">Severity {{ risk.severity }}</a-tag>
                <a-tag v-if="risk.likelihood">Likelihood {{ risk.likelihood }}</a-tag>
                <a-tag v-if="risk.requirement_gap" color="orange">Requirement Gap</a-tag>
              </a-space>
              <p>{{ risk.description }}</p>
              <a-typography-paragraph type="secondary">{{ risk.rationale }}</a-typography-paragraph>
              <a-button type="link" style="padding: 0" @click="showRiskWhy(risk)">
                <BulbOutlined /> Why Generated
              </a-button>
            </a-card>
          </div>
          <div style="margin-top: 20px; text-align: right">
            <a-tooltip :title="approvedRisks.length ? '' : '至少批准一项 Risk'">
              <a-button
                type="primary"
                :disabled="!actionAvailable('GENERATE_SCENARIOS') || !approvedRisks.length || !requirementQuery.data.value || !analysisQuery.data.value"
                @click="runScenarioGeneration"
              >
                生成 Scenarios
              </a-button>
            </a-tooltip>
          </div>
        </template>
      </a-card>
    </a-tab-pane>

    <a-tab-pane key="scenarios" tab="Scenarios">
      <a-card class="surface-card" :bordered="false">
        <a-skeleton v-if="scenarioBatchQuery.isPending.value && scenarioBatchId" active />
        <ErrorState
          v-else-if="scenarioBatchQuery.isError.value"
          :message="readableApiError(scenarioBatchQuery.error.value)"
          @retry="void scenarioBatchQuery.refetch()"
        />
        <a-empty v-else-if="!scenarioBatchQuery.data.value" description="尚未生成 Test Scenarios" />
        <template v-else>
          <div class="inline-actions">
            <div>
              <h2 class="section-title">Scenario Human Review Gate</h2>
              <span class="muted">先审阅“测什么/为什么”，再生成执行步骤。</span>
            </div>
            <ReviewActions
              :status="scenarioBatchQuery.data.value.review_status"
              :loading="busyAction === 'scenario-review'"
              :review-disabled="!actionAvailable('REVIEW_SCENARIOS') || !selectedScenarioIds.length"
              :regenerate-disabled="!actionAvailable('REGENERATE_SCENARIOS')"
              :approve-disabled="!selectedScenarioIds.length"
              @approve="void reviewScenarios('APPROVE')"
              @reject="void reviewScenarios('REJECT')"
              @regenerate="regenerateScenarios"
            />
          </div>
          <a-divider />
          <a-table
            :data-source="scenarioBatchQuery.data.value.scenarios"
            :pagination="false"
            :row-key="(scenario: TestScenario) => scenario.id"
            :columns="[
              { title: '选择', key: 'select', width: 72 },
              { title: 'Scenario', key: 'scenario', width: 300 },
              { title: 'Type', dataIndex: 'scenario_type', key: 'type', width: 130 },
              { title: 'Priority', dataIndex: 'priority', key: 'priority', width: 110 },
              { title: 'Expected Behavior', key: 'expected', width: 180 },
              { title: 'Review', key: 'review', width: 130 },
              { title: '', key: 'why', width: 140 },
            ]"
            :scroll="{ x: 990 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'select'">
                <a-checkbox
                  :aria-label="`选择 Scenario ${record.scenario_code}`"
                  :checked="selectedScenarioIds.includes(record.id)"
                  :disabled="['APPROVED', 'STALE', 'SUPERSEDED'].includes(record.review_status) || !actionAvailable('REVIEW_SCENARIOS')"
                  @change="toggleScenarioSelection(record.id, checkboxChecked($event))"
                />
              </template>
              <template v-else-if="column.key === 'scenario'">
                <strong>{{ record.title }}</strong>
                <div class="muted mono">{{ record.scenario_code }}</div>
                <div class="muted">{{ record.test_intent }}</div>
              </template>
              <template v-else-if="column.key === 'expected'">
                <StatusTag :status="record.expected_behavior_status" kind="expected" />
              </template>
              <template v-else-if="column.key === 'review'"><StatusTag :status="record.review_status" kind="review" /></template>
              <template v-else-if="column.key === 'why'"><a-button type="link" @click="showScenarioWhy(record)"><BulbOutlined /> Why Generated</a-button></template>
            </template>
          </a-table>
          <div class="muted" style="margin-top: 10px">
            已选择 {{ selectedScenarioIds.length }} 个待审 Scenario；审批只提交所选项。
          </div>
          <a-alert
            v-if="scenarioBatchQuery.data.value.scenarios.some((scenario) => scenario.expected_behavior_status !== 'DEFINED')"
            type="warning"
            show-icon
            message="部分 Scenario 的 Expected Behavior 尚未定义"
            description="允许保留测试意图，但 Test Case Agent 不会编造具体行为；相关用例批准前必须完成需求澄清。"
            style="margin-top: 18px"
          />
          <div style="margin-top: 20px; text-align: right">
            <a-tooltip :title="approvedScenarios.length ? '' : '至少批准一个 Scenario 才能生成 Test Case'">
              <a-button
                type="primary"
                :disabled="!actionAvailable('GENERATE_TEST_CASES') || !scenarioBatchQuery.data.value || !requirementQuery.data.value || !canGenerateTestCases(scenarioBatchQuery.data.value.scenarios)"
                @click="runTestCaseGeneration"
              >
                <SafetyCertificateOutlined /> 生成 Test Cases
              </a-button>
            </a-tooltip>
          </div>
        </template>
      </a-card>
    </a-tab-pane>

    <a-tab-pane key="testcases" tab="Test Cases">
      <a-card class="surface-card" :bordered="false">
        <a-skeleton v-if="testCaseBatchQuery.isPending.value && testCaseBatchId" active />
        <ErrorState
          v-else-if="testCaseBatchQuery.isError.value"
          :message="readableApiError(testCaseBatchQuery.error.value)"
          @retry="void testCaseBatchQuery.refetch()"
        />
        <a-empty v-else-if="!testCaseBatchQuery.data.value" description="尚未生成 Test Cases" />
        <template v-else>
          <div class="inline-actions">
            <div>
              <h2 class="section-title">Execution-ready Test Cases</h2>
              <span class="muted">只实现已批准 Scenario 的测试意图。</span>
            </div>
            <ReviewActions
              :status="testCaseBatchQuery.data.value.review_status"
              :loading="busyAction === 'testcase-review'"
              :review-disabled="!actionAvailable('REVIEW_TEST_CASES') || !selectedTestCaseIds.length"
              :regenerate-disabled="!actionAvailable('REGENERATE_TEST_CASES')"
              :approve-disabled="!selectedApprovableTestCaseIds.length"
              @approve="void reviewTestCases('APPROVE')"
              @reject="void reviewTestCases('REJECT')"
              @regenerate="regenerateTestCases"
            />
          </div>
          <a-alert
            v-if="clarificationCount > 0"
            type="error"
            show-icon
            :message="`${clarificationCount} 个 Expected Result 需要澄清`"
            description="AI 没有替需求编造错误提示、禁止策略或 UI 反馈。它们会保留为不可批准项，但不会阻塞同批次中执行就绪用例的审批。"
            style="margin: 18px 0"
          />
          <a-alert
            v-if="selectedTestCaseIds.length"
            type="info"
            show-icon
            :message="`已选择 ${selectedTestCaseIds.length} 项；其中 ${selectedApprovableTestCaseIds.length} 项可批准`"
            :description="selectedBlockedTestCaseCount ? `${selectedBlockedTestCaseCount} 项因 Expected Result 未定义或尚未执行就绪，将不会包含在批准请求中。` : '批准请求只提交当前选择的执行就绪用例。'"
            style="margin: 18px 0"
          />
          <a-divider v-else />
          <a-collapse accordion>
            <a-collapse-panel v-for="testCase in testCaseBatchQuery.data.value.test_cases" :key="testCase.id">
              <template #header>
                <a-space wrap>
                  <a-checkbox
                    :aria-label="`选择 Test Case ${testCase.test_case_code}`"
                    :checked="selectedTestCaseIds.includes(testCase.id)"
                    :disabled="['APPROVED', 'STALE', 'SUPERSEDED'].includes(testCase.review_status) || !actionAvailable('REVIEW_TEST_CASES')"
                    @click.stop
                    @change="toggleTestCaseSelection(testCase.id, checkboxChecked($event))"
                  />
                  <span class="mono">{{ testCase.test_case_code }}</span>
                  <strong>{{ testCase.title }}</strong>
                  <StatusTag :status="testCase.review_status" kind="review" />
                  <StatusTag v-if="testCase.expected_result_status" :status="testCase.expected_result_status" kind="expected" />
                </a-space>
              </template>
              <template #extra>
                <a-button type="link" @click.stop="showTestCaseWhy(testCase)"><BulbOutlined /> Why</a-button>
              </template>
              <a-descriptions :column="{ xs: 1, md: 3 }" size="small" bordered style="margin-bottom: 16px">
                <a-descriptions-item label="Scenario"><span class="mono">{{ testCase.scenario_id }}</span></a-descriptions-item>
                <a-descriptions-item label="Priority">{{ testCase.priority }}</a-descriptions-item>
                <a-descriptions-item label="Revision">{{ testCase.revision }}</a-descriptions-item>
                <a-descriptions-item label="Preconditions">{{ recordText(testCase.preconditions) }}</a-descriptions-item>
                <a-descriptions-item label="Configuration">{{ recordText(testCase.configuration) }}</a-descriptions-item>
                <a-descriptions-item label="Test Data">{{ recordText(testCase.test_data) }}</a-descriptions-item>
              </a-descriptions>
              <a-table
                :data-source="testCase.steps"
                :pagination="false"
                :row-key="(step: { step_no: number }) => step.step_no"
                :columns="[
                  { title: '#', dataIndex: 'step_no', key: 'step', width: 64 },
                  { title: 'Action', dataIndex: 'action', key: 'action' },
                  { title: 'Configuration', key: 'configuration', width: 180 },
                  { title: 'Test Data', dataIndex: 'test_data', key: 'data', width: 180 },
                  { title: 'Expected Result', key: 'expected', width: 320 },
                ]"
                :scroll="{ x: 920 }"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'configuration'">
                    {{ recordText(record.configuration) }}
                  </template>
                  <template v-else-if="column.key === 'data'">
                    {{ recordText(record.test_data) }}
                  </template>
                  <template v-else-if="column.key === 'expected'">
                    <div>{{ record.expected_result || '—' }}</div>
                    <StatusTag :status="record.expected_result_status" kind="expected" />
                  </template>
                </template>
              </a-table>
            </a-collapse-panel>
          </a-collapse>
        </template>
      </a-card>
    </a-tab-pane>

    <a-tab-pane key="traceability" tab="Traceability">
      <a-card class="surface-card" :bordered="false">
        <div class="inline-actions">
          <div>
            <h2 class="section-title">Requirement → Assertion → Risk → Scenario → Test Case</h2>
            <span class="muted">每个测试资产都能回答“为什么存在”。</span>
          </div>
          <BranchesOutlined style="font-size: 30px; color: #7c3aed" />
        </div>
        <a-divider />
        <a-skeleton v-if="traceabilityQuery.isPending.value" active />
        <ErrorState
          v-else-if="traceabilityQuery.isError.value"
          :message="readableApiError(traceabilityQuery.error.value)"
          @retry="void traceabilityQuery.refetch()"
        />
        <a-empty v-else-if="!traceabilityQuery.data.value?.nodes.length" description="暂无追溯关系" />
        <a-row v-else :gutter="[18, 18]">
          <a-col :xs="24" :xl="10">
            <a-card title="Nodes" size="small" class="asset-card">
              <a-list :data-source="traceabilityQuery.data.value?.nodes" size="small">
                <template #renderItem="{ item }">
                  <a-list-item>
                    <a-space><a-tag color="geekblue">{{ item.type }}</a-tag><span class="mono">{{ item.id }}</span><span>{{ item.label }}</span></a-space>
                  </a-list-item>
                </template>
              </a-list>
            </a-card>
          </a-col>
          <a-col :xs="24" :xl="14">
            <a-card title="Relations" size="small" class="asset-card">
              <a-table
                :data-source="traceabilityQuery.data.value?.relations"
                :pagination="false"
                :row-key="(relation: { source: string; relation: string; target: string }) => `${relation.source}-${relation.relation}-${relation.target}`"
                :columns="[
                  { title: 'Source', dataIndex: 'source', key: 'source' },
                  { title: 'Relation', dataIndex: 'relation', key: 'relation' },
                  { title: 'Target', dataIndex: 'target', key: 'target' },
                ]"
              />
            </a-card>
          </a-col>
        </a-row>
      </a-card>
    </a-tab-pane>
  </a-tabs>

  <WhyGeneratedDrawer
    v-model:open="whyOpen"
    :title="whyTitle"
    :reason="whyReason"
    :references="whyReferences"
    :trace="whyTrace"
  />
</template>

<style scoped>
.workflow-header {
  overflow: hidden;
}

.requirement-text {
  padding: 20px;
  border-left: 4px solid #8b5cf6;
  border-radius: 0 10px 10px 0;
  white-space: pre-wrap;
  background: #f8f7ff;
  font-size: 15px;
  line-height: 1.75;
}
</style>
