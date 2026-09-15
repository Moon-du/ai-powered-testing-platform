<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import {
  ApartmentOutlined,
  BarChartOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  HomeOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'

import { platformApi } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(false)

const projectId = computed(() => {
  const value = route.params.projectId
  return typeof value === 'string' ? value : null
})

const projectQuery = useQuery({
  queryKey: computed(() => ['project', projectId.value]),
  queryFn: () => {
    if (!projectId.value) throw new Error('Project ID is required')
    return platformApi.getProject(projectId.value)
  },
  enabled: computed(() => Boolean(projectId.value)),
})

const projectLabel = computed(() => projectQuery.data.value?.name ?? '项目工作区')

const selectedKey = computed(() => {
  if (route.name === 'project-overview') return 'overview'
  if (route.name === 'project-coverage') return 'coverage'
  if (route.name === 'project-requirements' || route.name === 'requirement-workspace') {
    return 'requirements'
  }
  return 'projects'
})

function navigate(key: string): void {
  if (key === 'projects') void router.push({ name: 'projects' })
  if (!projectId.value) return
  if (key === 'overview') {
    void router.push({ name: 'project-overview', params: { projectId: projectId.value } })
  }
  if (key === 'requirements') {
    void router.push({ name: 'project-requirements', params: { projectId: projectId.value } })
  }
  if (key === 'coverage') {
    void router.push({ name: 'project-coverage', params: { projectId: projectId.value } })
  }
}
</script>

<template>
  <a-layout class="app-shell">
    <a-layout-sider
      v-model:collapsed="collapsed"
      :collapsed-width="72"
      :trigger="null"
      class="app-sider"
      width="252"
    >
      <div class="brand" :class="{ 'brand--collapsed': collapsed }">
        <div class="brand__mark"><ApartmentOutlined /></div>
        <div v-if="!collapsed" class="brand__copy">
          <strong>Test Intelligence</strong>
          <span>AI 测试工程平台</span>
        </div>
      </div>

      <a-menu
        mode="inline"
        theme="light"
        :selected-keys="[selectedKey]"
        class="app-menu"
        @click="({ key }: { key: string }) => navigate(key)"
      >
        <a-menu-item v-if="!projectId" key="projects">
          <template #icon><FolderOpenOutlined /></template>
          项目
        </a-menu-item>
        <a-menu-item v-if="projectId" key="overview">
          <template #icon><ApartmentOutlined /></template>
          项目概览
        </a-menu-item>
        <a-menu-item v-if="projectId" key="requirements">
          <template #icon><FileTextOutlined /></template>
          需求与测试资产
        </a-menu-item>
        <a-menu-item v-if="projectId" key="coverage">
          <template #icon><BarChartOutlined /></template>
          覆盖率
        </a-menu-item>
      </a-menu>

      <div v-if="!collapsed" class="sider-principle">
        <SafetyCertificateOutlined />
        <div>
          <strong>Human Review Gate</strong>
          <span>批准 Scenario 后才生成 Test Case</span>
        </div>
      </div>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="app-header">
        <a-button type="text" class="collapse-button" @click="collapsed = !collapsed">
          <MenuUnfoldOutlined v-if="collapsed" />
          <MenuFoldOutlined v-else />
        </a-button>
        <nav class="app-breadcrumb" aria-label="当前位置">
          <button class="app-breadcrumb__link" type="button" @click="void router.push({ name: 'projects' })">
            <HomeOutlined />
            <span>主页面</span>
          </button>
          <template v-if="projectId">
            <span class="app-breadcrumb__separator">/</span>
            <button
              class="app-breadcrumb__link app-breadcrumb__link--current"
              type="button"
              @click="void router.push({ name: 'project-overview', params: { projectId } })"
            >
              {{ projectLabel }}
            </button>
          </template>
        </nav>
        <div class="app-header__spacer" />
        <a-tag color="purple">开发身份</a-tag>
        <span class="app-header__role">{{ auth.displayRole }}</span>
      </a-layout-header>
      <a-layout-content class="app-content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>
