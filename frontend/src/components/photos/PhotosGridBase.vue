<template>
  <div
    v-if="loading"
    class="pg-base__grid"
  >
    <div
      v-for="i in skeletonCount"
      :key="`pgsk-${i}`"
      class="pg-base__skeleton photo-skeleton"
    />
  </div>
  <div
    v-else-if="photos.length"
    class="pg-base__grid"
  >
    <div
      v-for="(p, idx) in photos"
      :key="p.id"
      class="pg-base__cell photo-cell"
      :class="cellClass ? cellClass(p) : undefined"
      draggable="false"
      role="button"
      tabindex="0"
      @click="$emit('photo-click', p, idx)"
      @keydown.enter="$emit('photo-click', p, idx)"
      @keydown.space.prevent="$emit('photo-click', p, idx)"
    >
      <slot
        name="cell"
        :photo="p"
        :idx="idx"
      />
    </div>
  </div>
  <slot
    v-else
    name="empty"
  />
</template>

<script setup lang="ts" generic="T extends { id: string }">
withDefaults(defineProps<{
  photos: T[]
  loading: boolean
  skeletonCount?: number
  cellClass?: (p: T) => string | undefined
}>(), {
  skeletonCount: 12,
  cellClass: undefined,
})

defineEmits<{
  'photo-click': [photo: T, idx: number]
}>()
</script>

<style scoped>
.pg-base__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.pg-base__cell {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--color-bg-muted);
  cursor: pointer;
}
.pg-base__skeleton {
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-border) 50%, var(--color-bg-muted) 75%);
  background-size: 200% 100%;
  animation: pgBaseSkel 1.4s infinite;
}
@keyframes pgBaseSkel { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
</style>
