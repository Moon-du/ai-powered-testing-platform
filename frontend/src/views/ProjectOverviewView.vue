<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { BarChartOutlined, EditOutlined, FileAddOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import { platformApi, readableApiError } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { ProjectContextItem, ProjectContextResponse } from '@/types'

type EditableProjectContextItem = Omit<ProjectContextItem, 'value'> & { value: string }

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const projectId = String(route.params.projectId)
const contextEditorOpen = ref(false)
const draftItems = ref<EditableProjectContextItem[]>([])

const projectQuery = useQuery({
  queryKey: ['project', projectId],
  queryFn: () => platformApi.getProject(projectId),
})
const contextQuery = useQuery({
  queryKey: ['project-context', projectId],
  queryFn: () => platformApi.getProjectContext(projectId),
})
const knowledgeQuery = useQuery({
  queryKey: ['knowledge-context', projectId],
  queryFn: () => platformApi.getKnowledgeContext(projectId),
})

const knowledgeCounts = computed(() => {
  const data = knowledgeQuery.data.value
  if (!data) return []
  const counts = data.summary ?? data.counts
  if (counts) return Object.entries(counts).map(([label, value]) => ({ label, value }))
  return [
    ['Modules', data.modules?.length ?? 0],
    ['Functions', data.functions?.length ?? 0],
    ['Risks', data.risks?.length ?? 0],
    ['Rules', data.rules?.length ?? 0],
    ['Patterns', data.patterns?.length ?? 0],
    ['Failure Modes', data.failure_modes?.length ?? 0],
  ].map(([label, value]) => ({ label: String(label), value: Number(value) }))
})

const saveContextMutation = useMutation({
  mutationFn: () =>
    platformApi.updateProjectContext(
      projectId,
      draftItems.value.filter((item) => item.name.trim() && String(item.value).trim()),
      contextQuery.data.value?.revision ?? 0,
    ),
  onSuccess: (data) => {
    queryClient.setQueryData<ProjectContextResponse>(['project-context', projectId], data)
    contextEditorOpen.value = false
    void message.success('Project Context 已更新')
  },
  onError: (error) => void message.error(readableApiError(error)),
})

function openContextEditor(): void {
  draftItems.value = (contextQuery.data.value?.items ?? []).map((item) => ({
    ...item,
    value: typeof item.value === 'string' ? item.value : JSON.stringify(item.value),
  }))
  contextEditorOpen.value = true
}

function addContextItem(): void {
  draftItems.value.push({ context_type: 'Configuration', name: '', value: '', status: 'Active' })
}
</script>

<template>
  <a-skeleton v-if="projectQuery.isPending.value" active :paragraph="{ rows: 9 }" />
  <ErrorState
    v-else-if="projectQuery.isError.value"
    :message="readableApiError(projectQuery.error.value)"
    @retry="void projectQuery.refetch()"
  />
  <template v-else-if="projectQuery.data.value">
    <PageHeader
      eyebrow="Project Overview"
      :title="projectQuery.data.value.name"
      :subtitle="projectQuery.data.value.description || '产品知识基线与项目差异上下文。'"
    >
      <template #actions>
        <a-button @click="void router.push({ name: 'project-coverage', params: { projectId } })">
          <template #icon><BarChartOutlined /></template>
          查看覆盖率
        </a-button>
        <a-button type="primary" @click="void router.push({ name: 'project-requirements', params: { projectId } })">
          <template #icon><FileAddOutlined /></template>
          管理需求
        </a-button>
      </template>
    </PageHeader>

    <a-row :gutter="[20, 20]">
      <a-col :xs="24" :xl="10">
        <a-card title="项目边界" class="surface-card" :bordered="false">
          <a-descriptions :column="1" bordered size="small">
            <a-descriptions-item label="Project Code"><span class="mono">{{ projectQuery.data.value.project_code }}</span></a-descriptions-item>
            <a-descriptions-item label="Product Type">
              {{ projectQuery.data.value.product_type?.display_name ?? projectQuery.data.value.product_type_id }}
            </a-descriptions-item>
            <a-descriptions-item label="Knowledge Pack">
              <a-tag color="geekblue">v{{ projectQuery.data.value.knowledge_pack_version }}</a-tag>
              <span class="mono">{{ projectQuery.data.value.knowledge_pack_id }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="Variant">{{ projectQuery.data.value.product_variant || '未指定' }}</a-descriptions-item>
            <a-descriptions-item label="项目版本">{{ projectQuery.data.value.project_version || '未指定' }}</a-descriptions-item>
            <a-descriptions-item label="状态"><StatusTag :status="projectQuery.data.value.status" kind="workflow" /></a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>

      <a-col :xs="24" :xl="14">
        <a-card title="Product Knowledge 摘要" class="surface-card" :bordered="false">
          <template #extra><a-tag color="blue">项目只读</a-tag></template>
          <a-skeleton v-if="knowledgeQuery.isPending.value" active />
          <ErrorState
            v-else-if="knowledgeQuery.isError.value"
            :message="readableApiError(knowledgeQuery.error.value)"
            @retry="void knowledgeQuery.refetch()"
          />
          <div v-else class="metric-grid">
            <a-statistic
              v-for="item in knowledgeCounts"
              :key="item.label"
              :title="item.label.replaceAll('_', ' ')"
              :value="item.value"
            />
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-card title="Project Context Overlay" class="surface-card" :bordered="false" style="margin-top: 20px">
      <template #extra>
        <a-button @click="openContextEditor">
          <template #icon><EditOutlined /></template>
          编辑 Context
        </a-button>
      </template>
      <a-skeleton v-if="contextQuery.isPending.value" active />
      <ErrorState
        v-else-if="contextQuery.isError.value"
        :message="readableApiError(contextQuery.error.value)"
        @retry="void contextQuery.refetch()"
      />
      <a-empty v-else-if="!(contextQuery.data.value?.items.length)" description="暂无项目差异上下文" />
      <a-table
        v-else
        :data-source="contextQuery.data.value?.items"
        :pagination="false"
        :row-key="(item: ProjectContextItem, index?: number) => item.id ?? `${item.context_type}-${index}`"
        :columns="[
          { title: '类型', dataIndex: 'context_type', key: 'type', width: 180 },
          { title: '名称', dataIndex: 'name', key: 'name', width: 220 },
          { title: '值', dataIndex: 'value', key: 'value' },
          { title: '优先级', dataIndex: 'priority', key: 'priority', width: 120 },
        ]"
      />
    </a-card>
  </template>

  <a-drawer v-model:open="contextEditorOpen" title="编辑 Project Context" width="min(720px, 94vw)">
    <a-alert
      type="warning"
      show-icon
      message="这里仅维护当前 Project 相对 Product Knowledge 的差异。"
      description="Changed/Excluded Function、Configuration、Special Risk、Known Issue 等不会反向修改 Product Knowledge。"
      style="margin-bottom: 18px"
    />
    <a-space direction="vertical" style="width: 100%" size="middle">
      <a-card v-for="(item, index) in draftItems" :key="index" size="small">
        <a-row :gutter="12">
          <a-col :span="8">
            <a-select v-model:value="item.context_type" style="width: 100%">
              <a-select-option v-for="type in ['Configuration', 'New Function', 'Changed Function', 'Excluded Function', 'Special Risk', 'Product Variant', 'Hardware Change', 'Software Change', 'Testing Constraint', 'Known Issue']" :key="type" :value="type">{{ type }}</a-select-option>
            </a-select>
          </a-col>
          <a-col :span="7"><a-input v-model:value="item.name" placeholder="名称" /></a-col>
          <a-col :span="7"><a-input v-model:value="item.value" placeholder="值或说明" /></a-col>
          <a-col :span="2"><a-button danger type="text" @click="draftItems.splice(index, 1)">删除</a-button></a-col>
        </a-row>
      </a-card>
      <a-button block @click="addContextItem">添加 Context 条目</a-button>
    </a-space>
    <template #footer>
      <div style="text-align: right">
        <a-space>
          <a-button @click="contextEditorOpen = false">取消</a-button>
          <a-button type="primary" :loading="saveContextMutation.isPending.value" @click="saveContextMutation.mutate()">保存 Overlay</a-button>
        </a-space>
      </div>
    </template>
  </a-drawer>
</template>
