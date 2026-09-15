<script setup lang="ts">
import { computed } from 'vue'

import type { AiRun } from '@/types'
import { clampPercent } from '@/utils/workflow'

const props = defineProps<{ run?: AiRun | null }>()

const running = computed(() => props.run?.status === 'QUEUED' || props.run?.status === 'RUNNING')
const percent = computed(() => clampPercent(props.run?.progress?.percent ?? (running.value ? 35 : 100)))
const alertType = computed(() => {
  if (props.run?.status === 'FAILED') return 'error'
  if (props.run?.status === 'SUCCEEDED') return 'success'
  return 'info'
})
const title = computed(() => {
  if (!props.run) return ''
  if (props.run.status === 'QUEUED') return 'AI 任务已排队'
  if (props.run.status === 'RUNNING') return 'AI 正在生成结构化测试资产'
  if (props.run.status === 'SUCCEEDED') return 'AI 任务已完成'
  return 'AI 任务失败'
})
</script>

<template>
  <section v-if="run" class="ai-run-panel" aria-live="polite">
    <a-alert :type="alertType" show-icon>
      <template #message>
        <a-space wrap>
          <strong>{{ title }}</strong>
          <a-tag>{{ run.task_type.replaceAll('_', ' ') }}</a-tag>
          <span class="mono">{{ run.id }}</span>
        </a-space>
      </template>
      <template #description>
        <div v-if="running" class="ai-run-panel__progress">
          <span>{{ run.progress?.stage?.replaceAll('_', ' ') ?? '准备上下文与知识' }}</span>
          <a-progress :percent="percent" :status="run.status === 'RUNNING' ? 'active' : 'normal'" />
        </div>
        <span v-else-if="run.status === 'FAILED'">
          {{ run.error?.message ?? '生成失败，请检查上下文后重试。' }}
        </span>
        <span v-else>结果已通过任务边界校验，正在刷新工作流。</span>
      </template>
    </a-alert>
  </section>
</template>
