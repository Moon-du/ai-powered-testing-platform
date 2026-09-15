<script setup lang="ts">
import KnowledgeReferenceList from '@/components/workflow/KnowledgeReferenceList.vue'
import type { KnowledgeReference } from '@/types'

withDefaults(
  defineProps<{
    open: boolean
    title?: string
    reason?: string
    references?: KnowledgeReference[]
    trace?: string[]
  }>(),
  { title: '为什么生成', reason: '', references: () => [], trace: () => [] },
)

defineEmits<{ 'update:open': [value: boolean] }>()
</script>

<template>
  <a-drawer
    :open="open"
    :title="title"
    width="min(560px, 92vw)"
    @close="$emit('update:open', false)"
  >
    <a-typography-title :level="5">生成依据</a-typography-title>
    <a-typography-paragraph>{{ reason || '未提供生成说明。' }}</a-typography-paragraph>

    <template v-if="trace.length">
      <a-divider />
      <a-typography-title :level="5">来源链</a-typography-title>
      <a-steps direction="vertical" size="small" :current="trace.length - 1">
        <a-step v-for="item in trace" :key="item" :title="item" />
      </a-steps>
    </template>

    <a-divider />
    <a-typography-title :level="5">Knowledge References</a-typography-title>
    <KnowledgeReferenceList :references="references" />
  </a-drawer>
</template>
