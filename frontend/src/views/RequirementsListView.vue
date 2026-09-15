<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ArrowLeftOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import { platformApi, readableApiError } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Requirement } from '@/types'
import { formatDateTime } from '@/utils/presentation'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const projectId = String(route.params.projectId)
const addOpen = ref(false)
const search = ref('')
const stage = ref<string>()
const form = reactive({ requirement_code: '', title: '', original_text: '' })

const projectQuery = useQuery({
  queryKey: ['project', projectId],
  queryFn: () => platformApi.getProject(projectId),
})
const requirementsQuery = useQuery({
  queryKey: ['requirements', projectId],
  queryFn: () => platformApi.listRequirements(projectId),
})

const filteredRequirements = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  return (requirementsQuery.data.value ?? []).filter((requirement) => {
    const matchesSearch =
      !term ||
      [requirement.requirement_code, requirement.title, requirement.original_text]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(term))
    const matchesStage = !stage.value || requirement.workflow_stage === stage.value
    return matchesSearch && matchesStage
  })
})

const createMutation = useMutation({
  mutationFn: () => platformApi.createRequirement(projectId, { ...form }),
  onSuccess: async (requirement) => {
    await queryClient.invalidateQueries({ queryKey: ['requirements', projectId] })
    addOpen.value = false
    Object.assign(form, { requirement_code: '', title: '', original_text: '' })
    void message.success('Requirement 已创建')
    void router.push({
      name: 'requirement-workspace',
      params: { projectId, requirementId: requirement.id },
    })
  },
  onError: (error) => void message.error(readableApiError(error)),
})

const columns = [
  { title: 'Requirement', key: 'requirement', width: 320 },
  { title: 'Revision', dataIndex: 'revision', key: 'revision', width: 100 },
  { title: 'Workflow', key: 'workflow', width: 180 },
  { title: '信号', key: 'signals', width: 220 },
  { title: '最近更新', key: 'updatedAt', width: 180 },
  { title: '', key: 'action', width: 92 },
]

function openRequirement(requirement: Requirement): void {
  void router.push({
    name: 'requirement-workspace',
    params: { projectId, requirementId: requirement.id },
  })
}

function submit(): void {
  if (!form.requirement_code.trim() || !form.title.trim() || !form.original_text.trim()) {
    void message.warning('Requirement Code、标题和 Original Text 为必填项')
    return
  }
  createMutation.mutate()
}
</script>

<template>
  <PageHeader
    eyebrow="Requirement Intelligence"
    :title="projectQuery.data.value ? `${projectQuery.data.value.name} · 需求` : '需求管理'"
    subtitle="Requirement 原文保持为事实；AI Analysis、Risk、Scenario 和 Case 作为可审阅、可追溯的衍生资产。"
  >
    <template #actions>
      <a-button @click="void router.push({ name: 'project-overview', params: { projectId } })">
        <template #icon><ArrowLeftOutlined /></template>
        项目概览
      </a-button>
      <a-button type="primary" @click="addOpen = true">
        <template #icon><PlusOutlined /></template>
        手工新增
      </a-button>
    </template>
  </PageHeader>

  <a-card class="surface-card" :bordered="false">
    <div class="inline-actions" style="margin-bottom: 18px">
      <a-space wrap>
        <a-input v-model:value="search" allow-clear placeholder="搜索代码、标题或原文" style="width: 320px">
          <template #prefix><SearchOutlined class="muted" /></template>
        </a-input>
        <a-select v-model:value="stage" allow-clear placeholder="Workflow Stage" style="width: 210px">
          <a-select-option v-for="item in ['IMPORTED', 'ANALYZING', 'ANALYSIS_REVIEW', 'RISK_REVIEW', 'SCENARIO_REVIEW', 'TESTCASE_REVIEW', 'READY', 'STALE', 'BLOCKED']" :key="item" :value="item">{{ item.replaceAll('_', ' ') }}</a-select-option>
        </a-select>
      </a-space>
      <span class="muted">{{ filteredRequirements.length }} 条</span>
    </div>

    <a-skeleton v-if="requirementsQuery.isPending.value" active :paragraph="{ rows: 7 }" />
    <ErrorState
      v-else-if="requirementsQuery.isError.value"
      :message="readableApiError(requirementsQuery.error.value)"
      @retry="void requirementsQuery.refetch()"
    />
    <a-empty v-else-if="!filteredRequirements.length" description="暂无 Requirement">
      <a-button type="primary" @click="addOpen = true">新增第一条 Requirement</a-button>
    </a-empty>
    <a-table
      v-else
      :columns="columns"
      :data-source="filteredRequirements"
      :row-key="(record: Requirement) => record.id"
      :scroll="{ x: 1080 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'requirement'">
          <a-button type="link" class="requirement-link" @click="openRequirement(record)">
            {{ record.title || record.requirement_code }}
          </a-button>
          <div class="muted mono">{{ record.requirement_code }}</div>
        </template>
        <template v-else-if="column.key === 'workflow'">
          <StatusTag :status="record.workflow_stage ?? record.status" kind="workflow" />
        </template>
        <template v-else-if="column.key === 'signals'">
          <a-space wrap>
            <a-tag v-if="record.has_gaps" color="orange">Requirement Gap</a-tag>
            <a-tag v-if="record.stale || record.review_status === 'STALE'" color="volcano">STALE</a-tag>
            <span v-if="!record.has_gaps && !record.stale" class="muted">—</span>
          </a-space>
        </template>
        <template v-else-if="column.key === 'updatedAt'">{{ formatDateTime(record.updated_at ?? record.created_at) }}</template>
        <template v-else-if="column.key === 'action'"><a-button @click="openRequirement(record)">打开</a-button></template>
      </template>
    </a-table>
  </a-card>

  <a-modal v-model:open="addOpen" title="手工新增 Requirement" :confirm-loading="createMutation.isPending.value" @ok="submit">
    <a-form :model="form" layout="vertical">
      <a-form-item label="Requirement Code" required>
        <a-input v-model:value="form.requirement_code" placeholder="REQ-001" />
      </a-form-item>
      <a-form-item label="标题" required>
        <a-input v-model:value="form.title" placeholder="简短描述需求意图" />
      </a-form-item>
      <a-form-item label="Original Text" required>
        <a-textarea v-model:value="form.original_text" :rows="7" placeholder="粘贴原始需求。AI 不会覆盖此事实文本。" />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.requirement-link {
  height: auto;
  padding: 0;
  color: #6d28d9;
  font-weight: 700;
  white-space: normal;
  text-align: left;
}
</style>
