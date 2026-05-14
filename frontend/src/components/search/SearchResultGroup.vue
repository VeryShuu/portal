<template>
  <div v-if="items.length" class="gs__group">
    <div class="gs__group-title">{{ title }}</div>
    <button
      v-for="(item, i) in items"
      :key="getKey(item)"
      type="button"
      role="option"
      :aria-selected="activeIndex === offset + i"
      class="gs__item"
      :class="{ 'gs__item--active': activeIndex === offset + i }"
      @mouseenter="$emit('hover', offset + i)"
      @click="$emit('pick', item)"
    >
      <n-icon size="16" class="gs__item-icon"><component :is="icon" /></n-icon>
      <span class="gs__item-title">{{ getTitle(item) }}</span>
      <span v-if="getMeta(item)" class="gs__item-meta">{{ getMeta(item) }}</span>
    </button>
  </div>
</template>

<script setup lang="ts" generic="T">
import { NIcon } from 'naive-ui'

defineProps<{
  title: string
  icon: unknown
  items: T[]
  offset: number
  activeIndex: number
  getKey: (item: T) => string
  getTitle: (item: T) => string
  getMeta: (item: T) => string | null | undefined
}>()

defineEmits<{
  hover: [index: number]
  pick: [item: T]
}>()
</script>
