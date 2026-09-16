<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { DeleteOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'

import { platformApi, readableApiError } from '@/api/client'
import ErrorState from '@/components/common/ErrorState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { Project } from '@/types'
import { formatDateTime } from '@/utils/presentation'

const router = useRouter()
const queryClient = useQueryClient()
const search = ref('')

const {
  data: projects,
  error,
  isError,
  isPending,
  refetch,
} = useQuery({
  queryKey: ['projects'],
  queryFn: platformApi.listProjects,
})

const filteredProjects = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  if (!term) return projects.value ?? []
  return (projects.value ?? []).filter((project) =>
    [project.name, project.project_code, project.product_type?.display_name, project.product_variant]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase().includes(term)),
  )
})

const columns = [
  { title: '项目', key: 'project', width: 280 },
  { title: '产品类型', key: 'productType', width: 180 },
  { title: 'Knowledge Pack', key: 'pack', width: 190 },
  { title: 'Variant', dataIndex: 'product_variant', key: 'variant', width: 150 },
  { title: '状态', key: 'status', width: 110 },
  { title: '最近更新', key: 'updatedAt', width: 180 },
  { title: '操作', key: 'action', width: 150, fixed: 'right' as const },
]

function openProject(project: Project): void {
  void router.push({ name: 'project-overview', params: { projectId: project.id } })
}

const deleteMutation = useMutation({
  mutationFn: (projectId: string) => platformApi.deleteProject(projectId),
  onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['projects'] })
    void message.success('项目及其全部内容已删除')
  },
  onError: (error) => void message.error(readableApiError(error)),
})

function confirmDelete(project: Project): void {
  Modal.confirm({
    title: `删除项目“${project.name}”？`,
    content: '该项目下的需求、AI 分析、风险、场景、测试用例、运行记录、项目上下文及项目私有 Product Knowledge 都会永久删除，此操作无法撤销。',
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => deleteMutation.mutateAsync(project.id),
  })
}
</script>

<template>
  <PageHeader
    eyebrow="P0 Project Workspace"
    title="项目"
    subtitle="每个项目固定一个 Product Type 与 Knowledge Pack 版本，并在严格隔离的上下文中管理需求与测试资产。"
  >
    <template #actions>
      <a-button type="primary" size="large" @click="void router.push({ name: 'project-create' })">
        <template #icon><PlusOutlined /></template>
        创建项目
      </a-button>
    </template>
  </PageHeader>

  <a-card class="surface-card" :bordered="false">
    <div class="inline-actions" style="margin-bottom: 18px">
      <a-input v-model:value="search" allow-clear placeholder="搜索项目、代码或产品类型" style="max-width: 380px">
        <template #prefix><SearchOutlined class="muted" /></template>
      </a-input>
      <span class="muted">{{ filteredProjects.length }} 个项目</span>
    </div>

    <a-skeleton v-if="isPending" active :paragraph="{ rows: 7 }" />
    <ErrorState v-else-if="isError" :message="readableApiError(error)" @retry="void refetch()" />
    <a-empty v-else-if="!filteredProjects.length" description="还没有项目，先创建第一条垂直业务链路。">
      <a-button type="primary" @click="void router.push({ name: 'project-create' })">创建项目</a-button>
    </a-empty>
    <a-table
      v-else
      :columns="columns"
      :data-source="filteredProjects"
      :row-key="(record: Project) => record.id"
      :scroll="{ x: 1120 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'project'">
          <a-button type="link" class="project-link" @click="openProject(record)">
            {{ record.name }}
          </a-button>
          <div class="muted mono">{{ record.project_code }}</div>
        </template>
        <template v-else-if="column.key === 'productType'">
          {{ record.product_type?.display_name ?? record.product_type?.name ?? 'custom' }}
        </template>
        <template v-else-if="column.key === 'pack'">
          <template v-if="record.knowledge_pack_version">
            <strong>{{ record.knowledge_pack_version }}</strong>
            <div class="muted mono">{{ record.knowledge_pack_id }}</div>
          </template>
          <span v-else>None</span>
        </template>
        <template v-else-if="column.key === 'status'">
          <StatusTag :status="record.status" kind="workflow" />
        </template>
        <template v-else-if="column.key === 'updatedAt'">
          {{ formatDateTime(record.updated_at ?? record.created_at) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <a-space>
            <a-button @click="openProject(record)">打开</a-button>
            <a-button danger :loading="deleteMutation.isPending.value" @click="confirmDelete(record)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </a-space>
        </template>
      </template>
    </a-table>
  </a-card>
</template>

<style scoped>
.project-link {
  height: auto;
  padding: 0;
  color: #6d28d9;
  font-size: 15px;
  font-weight: 700;
}
</style>
