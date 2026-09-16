<script setup lang="ts">
import type { ReviewStatus } from '@/types'

withDefaults(
  defineProps<{
    status?: ReviewStatus | null
    loading?: boolean
    regenerate?: boolean
    disabled?: boolean
    reviewDisabled?: boolean
    regenerateDisabled?: boolean
    approveDisabled?: boolean
  }>(),
  {
    status: null,
    loading: false,
    regenerate: true,
    disabled: false,
    reviewDisabled: false,
    regenerateDisabled: false,
    approveDisabled: false,
  },
)

defineEmits<{
  approve: []
  reject: []
  regenerate: []
}>()
</script>

<template>
  <a-space wrap>
    <a-button
      type="primary"
      :loading="loading"
      :disabled="disabled || reviewDisabled || approveDisabled || status === 'APPROVED' || status === 'STALE'"
      @click="$emit('approve')"
    >
      批准
    </a-button>
    <a-button danger :disabled="disabled || reviewDisabled || loading || status === 'REJECTED'" @click="$emit('reject')">拒绝</a-button>
    <a-button v-if="regenerate" :disabled="disabled || regenerateDisabled || loading" @click="$emit('regenerate')">
      重新生成
    </a-button>
  </a-space>
</template>
