<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { ArrowLeftOutlined, WarningOutlined } from '@ant-design/icons-vue'

import { platformApi, readableApiError } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import type { CoverageMetric } from '@/types'
import { clampPercent } from '@/utils/workflow'

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.projectId)

const projectQuery = useQuery({
  queryKey: ['project', projectId],
  queryFn: () => platformApi.getProject(projectId),
})
const coverageQuery = useQuery({
  queryKey: ['coverage', projectId],
  queryFn: () => platformApi.getCoverage(projectId),
})

const coverageCards = computed(() => {
  const coverage = coverageQuery.data.value
  if (!coverage) return []
  return [
    { title: 'Requirements', metric: coverage.requirements, color: '#7c3aed' },
    { title: 'Assertion Coverage', metric: coverage.assertion_coverage, color: '#8b5cf6' },
    { title: 'Risk Coverage', metric: coverage.risk_coverage, color: '#a855f7' },
    { title: 'Approved Scenarios', metric: coverage.scenario, color: '#6366f1' },
    { title: 'Approved Test Cases', metric: coverage.test_cases, color: '#06b6d4' },
  ]
})

function percent(metric: CoverageMetric): number {
  if (metric.percentage != null) return clampPercent(metric.percentage)
  const completed = metric.covered ?? metric.approved ?? metric.analyzed ?? 0
  return metric.total ? clampPercent((completed / metric.total) * 100) : 0
}

function completed(metric: CoverageMetric): number {
  return metric.covered ?? metric.approved ?? metric.analyzed ?? 0
}
</script>

<template>
  <PageHeader
    eyebrow="Traceability & Coverage"
    :title="projectQuery.data.value ? `${projectQuery.data.value.name} · 覆盖率` : '项目覆盖率'"
    subtitle="覆盖率下钻到 Atomic Assertion 与 Requirement Risk，避免“Requirement 看似已覆盖、约束实际遗漏”的假覆盖。"
  >
    <template #actions>
      <a-button @click="void router.push({ name: 'project-overview', params: { projectId } })">
        <template #icon><ArrowLeftOutlined /></template>
        项目概览
      </a-button>
    </template>
  </PageHeader>

  <a-skeleton v-if="coverageQuery.isPending.value" active :paragraph="{ rows: 10 }" />
  <ErrorState
    v-else-if="coverageQuery.isError.value"
    :message="readableApiError(coverageQuery.error.value)"
    @retry="void coverageQuery.refetch()"
  />
  <template v-else-if="coverageQuery.data.value">
    <div class="coverage-grid">
      <a-card v-for="card in coverageCards" :key="card.title" class="surface-card coverage-card" :bordered="false">
        <a-progress type="dashboard" :percent="percent(card.metric)" :stroke-color="card.color" :size="112" />
        <div class="coverage-card__meta">
          <strong>{{ card.title }}</strong>
          <span>{{ completed(card.metric) }} / {{ card.metric.total }}</span>
        </div>
      </a-card>
    </div>

    <a-card title="Quality Gaps" class="surface-card" :bordered="false" style="margin-top: 20px">
      <div class="metric-grid">
        <a-statistic title="Requirement Gaps" :value="coverageQuery.data.value.issues.requirement_gaps">
          <template #prefix><WarningOutlined style="color: #fa8c16" /></template>
        </a-statistic>
        <a-statistic title="Undefined Expected Behaviors" :value="coverageQuery.data.value.issues.undefined_expected_behaviors">
          <template #prefix><WarningOutlined style="color: #cf1322" /></template>
        </a-statistic>
        <a-statistic title="STALE Assets" :value="coverageQuery.data.value.issues.stale_assets">
          <template #prefix><WarningOutlined style="color: #d46b08" /></template>
        </a-statistic>
      </div>
    </a-card>
  </template>
</template>

<style scoped>
.coverage-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  align-items: stretch;
  gap: 14px;
}

.coverage-card {
  height: 100%;
}

.coverage-card :deep(.ant-card-body) {
  display: flex;
  min-width: 0;
  height: 100%;
  min-height: 252px;
  padding: 22px 16px 18px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
}

.coverage-card__meta {
  width: 100%;
  min-width: 0;
}

.coverage-card strong,
.coverage-card span {
  display: block;
}

.coverage-card strong {
  min-height: 40px;
  margin-bottom: 4px;
  color: #273142;
  font-size: 14px;
  line-height: 20px;
  overflow-wrap: anywhere;
}

.coverage-card span {
  color: #8a94a6;
  font-size: 13px;
}

@media (max-width: 1180px) {
  .coverage-grid {
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  }
}
</style>
