<script setup lang="ts">
import { computed } from 'vue'

import type { ExpectedBehaviorStatus, ReviewStatus } from '@/types'
import { expectedStatusPresentation, reviewStatusPresentation } from '@/utils/workflow'

const props = defineProps<{
  status?: ReviewStatus | ExpectedBehaviorStatus | string | null
  kind?: 'review' | 'expected' | 'workflow'
}>()

const presentation = computed(() => {
  if (props.kind === 'expected') {
    return expectedStatusPresentation(props.status as ExpectedBehaviorStatus | undefined)
  }
  if (props.kind === 'review') {
    return reviewStatusPresentation(props.status as ReviewStatus | undefined)
  }
  if (props.status === 'STALE') return { label: '已过期', color: 'orange' }
  if (props.status === 'BLOCKED') return { label: '受阻', color: 'red' }
  if (props.status === 'READY') return { label: '可交付', color: 'green' }
  return { label: props.status?.replaceAll('_', ' ') ?? '未开始', color: 'blue' }
})
</script>

<template>
  <a-tag :color="presentation.color" class="status-tag">{{ presentation.label }}</a-tag>
</template>
