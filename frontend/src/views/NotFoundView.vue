<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <main class="not-found">
    <a-result status="404" title="404" sub-title="未找到这个工作台页面。">
      <template #extra><a-button type="primary" @click="void router.push({ name: 'projects' })">返回项目</a-button></template>
    </a-result>
  </main>
</template>

<style scoped>
.not-found {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: #f5f6f8;
}
</style>
