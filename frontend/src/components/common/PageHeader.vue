<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
  eyebrow?: string
}>()
</script>

<template>
  <header class="page-heading">
    <div>
      <p v-if="eyebrow" class="page-heading__eyebrow">{{ eyebrow }}</p>
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="page-heading__subtitle">{{ subtitle }}</p>
    </div>
    <a-space wrap>
      <slot name="actions" />
    </a-space>
  </header>
</template>
