<script setup lang="ts">
defineProps<{ message?: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <a-result status="error" title="加载失败" :sub-title="message ?? '服务暂时不可用，请稍后重试。'">
    <template #extra>
      <a-button type="primary" @click="$emit('retry')">重新加载</a-button>
    </template>
  </a-result>
</template>
