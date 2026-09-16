<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { ArrowLeftOutlined, CheckCircleFilled, UploadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

import { platformApi, readableApiError } from '@/api/client'
import PageHeader from '@/components/common/PageHeader.vue'

interface CreateProjectInput {
  project_code: string
  name: string
  description?: string
  product_type_id?: string
  product_type_code?: string
  knowledge_pack_id?: string
  knowledge_pack_version?: string
  product_variant?: string
  project_version?: string
}

const router = useRouter()
const currentStep = ref(0)
const pendingKnowledgeFiles = ref<File[]>([])
const pendingKnowledgeTexts = ref<Array<{ title: string; content: string }>>([])
const form = reactive<CreateProjectInput>({
  project_code: '',
  name: '',
  description: '',
  product_type_id: '',
  product_type_code: '',
  knowledge_pack_id: '',
  knowledge_pack_version: '',
  product_variant: '',
  project_version: 'V1.0',
})

const productTypesQuery = useQuery({
  queryKey: ['product-types'],
  queryFn: platformApi.listProductTypes,
})

const packsQuery = useQuery({
  queryKey: computed(() => ['knowledge-packs', form.product_type_id]),
  queryFn: () => platformApi.listKnowledgePacks(form.product_type_id),
  enabled: computed(() => Boolean(form.product_type_id)),
})

watch(
  () => form.product_type_id,
  () => {
    form.product_type_code = selectedProductType.value?.code ?? ''
    form.knowledge_pack_id = ''
    form.knowledge_pack_version = ''
  },
)

const selectedProductType = computed(() =>
  productTypesQuery.data.value?.find((item) => item.id === form.product_type_id),
)
const selectedPack = computed(() =>
  packsQuery.data.value?.find((item) => item.id === form.knowledge_pack_id),
)
const pendingKnowledgeCount = computed(
  () => pendingKnowledgeFiles.value.length + pendingKnowledgeTexts.value.filter((item) => item.content.trim()).length,
)

const stepReady = computed(() => {
  if (currentStep.value === 0 || currentStep.value === 1) return true
  if (currentStep.value === 2) return Boolean(form.name.trim() && form.project_code.trim())
  return true
})

const createMutation = useMutation({
  mutationFn: (input: CreateProjectInput) => platformApi.createProject(input),
  onSuccess: async (project) => {
    try {
      const textFiles = pendingKnowledgeTexts.value
        .filter((item) => item.content.trim())
        .map((item, index) => new File(
          [item.content],
          `${item.title.trim() || `knowledge-${index + 1}`}.txt`,
          { type: 'text/plain;charset=utf-8' },
        ))
      const files = [...pendingKnowledgeFiles.value, ...textFiles]
      if (files.length) {
        await platformApi.uploadProjectKnowledge(project.id, files, false)
      }
      void message.success('项目已创建')
    } catch (error) {
      void message.error(`项目已创建，但 Product Knowledge 上传失败：${readableApiError(error)}`)
    } finally {
      void router.push({ name: 'project-overview', params: { projectId: project.id } })
    }
  },
  onError: (error) => void message.error(readableApiError(error)),
})

function choosePack(packId: string): void {
  const pack = packsQuery.data.value?.find((item) => item.id === packId)
  if (!pack) return
  form.knowledge_pack_id = pack.id
  form.knowledge_pack_version = pack.version
}

async function stageKnowledgeFile(file: File): Promise<boolean> {
  pendingKnowledgeFiles.value.push(file)
  void message.success(`已暂存 ${file.name}，创建项目后上传`)
  return false
}

function removeKnowledgeFile(index: number): void {
  pendingKnowledgeFiles.value.splice(index, 1)
}

function addKnowledgeText(): void {
  pendingKnowledgeTexts.value.push({ title: '', content: '' })
}

function next(): void {
  if (!stepReady.value) {
    void message.warning('请先完成当前步骤的必填信息')
    return
  }
  currentStep.value = Math.min(3, currentStep.value + 1)
}

function submit(): void {
  createMutation.mutate({ ...form })
}
</script>

<template>
  <PageHeader
    eyebrow="Create Project Wizard"
    title="创建项目"
    subtitle="先确定产品类型与知识基线，再补充项目差异上下文。Knowledge Pack 版本会在创建时固定。"
  >
    <template #actions>
      <a-button @click="void router.push({ name: 'projects' })">
        <template #icon><ArrowLeftOutlined /></template>
        返回项目列表
      </a-button>
    </template>
  </PageHeader>

  <a-card class="surface-card wizard-card" :bordered="false">
    <a-steps
      :current="currentStep"
      :items="[
        { title: '产品类型', description: '选择 Product Type' },
        { title: '知识包', description: '固定 Pack Version' },
        { title: '项目信息', description: '名称、代码与 Variant' },
        { title: '确认创建', description: '检查业务边界' },
      ]"
    />
    <a-divider />

    <section v-if="currentStep === 0">
      <h2 class="section-title">选择 Product Type</h2>
      <a-alert message="Product Type 决定 AI 使用哪套垂直产品知识。" type="info" show-icon style="margin-bottom: 18px" />
      <a-skeleton v-if="productTypesQuery.isPending.value" active />
      <div v-else class="choice-grid">
        <button
          type="button"
          class="choice-card"
          :class="{ 'choice-card--selected': !form.product_type_id }"
          @click="form.product_type_id = ''"
        >
          <a-space>
            <strong>暂不选择 Product Type</strong>
            <CheckCircleFilled v-if="!form.product_type_id" style="color: #7c3aed" />
          </a-space>
          <span>先创建未分类项目，后续再补充产品类型与 Knowledge Pack。</span>
        </button>
        <button
          v-for="productType in productTypesQuery.data.value ?? []"
          :key="productType.id"
          type="button"
          class="choice-card"
          :class="{ 'choice-card--selected': form.product_type_id === productType.id }"
          @click="form.product_type_id = productType.id"
        >
          <a-space>
            <strong>{{ productType.display_name }}</strong>
            <CheckCircleFilled v-if="form.product_type_id === productType.id" style="color: #7c3aed" />
          </a-space>
          <span>{{ productType.name }}</span>
          <span>{{ productType.description || '垂直产品知识与测试模式' }}</span>
        </button>
      </div>
    </section>

    <section v-else-if="currentStep === 1">
      <h2 class="section-title">选择 Knowledge Pack</h2>
      <a-alert
        :message="`${selectedProductType?.display_name ?? '当前产品'} 的 Published Knowledge Pack`"
        description="项目引用该版本，不复制知识；后续 Pack 更新不会静默改变本项目。"
        type="info"
        show-icon
        style="margin-bottom: 18px"
      />
      <a-skeleton v-if="packsQuery.isFetching.value" active />
      <template v-else>
        <a-upload :show-upload-list="false" accept=".txt,.md,.markdown,.docx,image/png,image/jpeg,image/webp" :before-upload="stageKnowledgeFile">
          <a-button style="margin-bottom: 18px">
            <template #icon><UploadOutlined /></template>
            上传文本、Word 或图片
          </a-button>
        </a-upload>
        <a-button style="margin: 0 0 18px 10px" @click="addKnowledgeText">新增纯文本知识</a-button>
        <a-list v-if="pendingKnowledgeFiles.length" bordered size="small" style="margin-bottom: 16px">
          <a-list-item v-for="(file, index) in pendingKnowledgeFiles" :key="`${file.name}-${index}`">
            {{ file.name }}
            <template #actions>
              <a-button type="link" danger @click="removeKnowledgeFile(index)">删除</a-button>
            </template>
          </a-list-item>
        </a-list>
        <a-space v-if="pendingKnowledgeTexts.length" direction="vertical" size="middle" style="width: 100%; margin-bottom: 16px">
          <a-card v-for="(item, index) in pendingKnowledgeTexts" :key="index" size="small">
            <a-input v-model:value="item.title" placeholder="知识标题（可选）" style="margin-bottom: 10px" />
            <a-textarea v-model:value="item.content" :rows="4" placeholder="输入 Product Knowledge 内容" />
            <a-button type="link" danger style="padding-left: 0; margin-top: 6px" @click="pendingKnowledgeTexts.splice(index, 1)">删除该条目</a-button>
          </a-card>
        </a-space>
        <div class="choice-grid">
          <button
            v-for="pack in packsQuery.data.value ?? []"
            :key="pack.id"
            type="button"
            class="choice-card"
            :class="{ 'choice-card--selected': form.knowledge_pack_id === pack.id }"
            @click="choosePack(pack.id)"
          >
            <a-space>
              <strong>{{ pack.name }}</strong>
              <a-tag color="geekblue">v{{ pack.version }}</a-tag>
            </a-space>
            <span>{{ pack.description || '产品模块、功能、风险、规则、模式与 Failure Mode' }}</span>
            <span v-if="pack.summary">
              {{ Object.entries(pack.summary).map(([key, value]) => `${key} ${value}`).join(' · ') }}
            </span>
          </button>
        </div>
        <a-empty
          v-if="!(packsQuery.data.value ?? []).length && !pendingKnowledgeCount"
          description="暂无 Knowledge Pack，可上传或暂时跳过"
        />
      </template>
    </section>

    <section v-else-if="currentStep === 2">
      <h2 class="section-title">填写项目信息</h2>
      <a-form :model="form" layout="vertical" class="project-form">
        <a-row :gutter="20">
          <a-col :xs="24" :md="12">
            <a-form-item label="项目名称" required>
              <a-input v-model:value="form.name" placeholder="例如 EP Volume Control V2" />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item label="项目代码" required>
              <a-input v-model:value="form.project_code" placeholder="例如 EP-VOL-V2" />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item label="项目版本">
              <a-input v-model:value="form.project_version" placeholder="V1.0" />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item label="Product Variant">
              <a-input v-model:value="form.product_variant" placeholder="例如 8-channel / 230V" />
            </a-form-item>
          </a-col>
          <a-col :span="24">
            <a-form-item label="说明">
              <a-textarea v-model:value="form.description" :rows="4" placeholder="项目目标与范围" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </section>

    <section v-else>
      <h2 class="section-title">确认项目业务边界</h2>
      <a-result status="info" title="准备创建项目" sub-title="创建后 Product Type 与 Knowledge Pack Version 会持久化固定。" />
      <a-descriptions bordered :column="{ xs: 1, md: 2 }">
        <a-descriptions-item label="Product Type">
          {{ selectedProductType ? `${selectedProductType.display_name} / ${selectedProductType.name}` : '暂未选择' }}
        </a-descriptions-item>
        <a-descriptions-item label="Knowledge Pack">
          {{ selectedPack ? `${selectedPack.name} · v${selectedPack.version}` : pendingKnowledgeCount ? `创建后保存 ${pendingKnowledgeCount} 条知识并生成 v1` : '暂未绑定' }}
        </a-descriptions-item>
        <a-descriptions-item label="项目">{{ form.name }} ({{ form.project_code }})</a-descriptions-item>
        <a-descriptions-item label="Variant">{{ form.product_variant || '未指定' }}</a-descriptions-item>
        <a-descriptions-item label="项目版本">{{ form.project_version || '未指定' }}</a-descriptions-item>
        <a-descriptions-item label="说明">{{ form.description || '未填写' }}</a-descriptions-item>
      </a-descriptions>
    </section>

    <a-divider />
    <div class="wizard-actions">
      <a-button v-if="currentStep > 0" @click="currentStep -= 1">上一步</a-button>
      <a-button v-if="currentStep < 3" type="primary" :disabled="!stepReady" @click="next">下一步</a-button>
      <a-button v-else type="primary" :loading="createMutation.isPending.value" @click="submit">创建并进入项目</a-button>
    </div>
  </a-card>
</template>

<style scoped>
.wizard-card {
  max-width: 1120px;
  margin: 0 auto;
}

.wizard-card section {
  min-height: 350px;
  padding: 8px 4px;
}

.project-form {
  max-width: 860px;
}

.wizard-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
