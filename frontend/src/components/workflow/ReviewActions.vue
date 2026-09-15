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
    <a-popconfirm title="确认拒绝当前版本？" ok-text="拒绝" cancel-text="取消" @confirm="$emit('reject')">
      <a-button danger :disabled="disabled || reviewDisabled || loading || status === 'REJECTED'">拒绝</a-button>
    </a-popconfirm>
    <a-button v-if="regenerate" :disabled="disabled || regenerateDisabled || loading" @click="$emit('regenerate')">
      重新生成
    </a-button>
  </a-space>
</template>
