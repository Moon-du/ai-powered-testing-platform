<script setup lang="ts">
import type { KnowledgeReference } from '@/types'

withDefaults(
  defineProps<{
    references?: KnowledgeReference[]
    compact?: boolean
  }>(),
  { references: () => [], compact: false },
)
</script>

<template>
  <a-empty v-if="!references.length" description="暂无知识引用" />
  <a-list v-else :data-source="references" :size="compact ? 'small' : 'default'">
    <template #renderItem="{ item }">
      <a-list-item>
        <a-list-item-meta :description="item.reason">
          <template #title>
            <a-space wrap>
              <a-tag color="geekblue">{{ item.knowledge_type }}</a-tag>
              <strong>{{ item.knowledge_id }}</strong>
              <span v-if="item.knowledge_version" class="muted">v{{ item.knowledge_version }}</span>
              <a-tag v-if="item.relevance_score != null">
                相关度 {{ Math.round(item.relevance_score * 100) }}%
              </a-tag>
            </a-space>
          </template>
        </a-list-item-meta>
      </a-list-item>
    </template>
  </a-list>
</template>
