<template>
  <div class="skeleton-card" :class="{ 'skeleton-card--news': variant === 'news' }">
    <div v-if="variant === 'news'" class="skeleton-card__cover" />
    <div class="skeleton-card__body">
      <div class="sk-line sk-line--title" />
      <div class="sk-line sk-line--short" />
      <div class="sk-line sk-line--full" />
      <div class="sk-line sk-line--full" />
      <div class="sk-line sk-line--meta" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ variant?: 'news' | 'list' }>()
</script>

<style scoped>
.skeleton-card {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  overflow: hidden;
}
.skeleton-card__cover {
  height: 180px;
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-bg) 37%, var(--color-bg-muted) 63%);
  background-size: 400% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
.skeleton-card__body {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sk-line {
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-bg) 37%, var(--color-bg-muted) 63%);
  background-size: 400% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
.sk-line--title { height: 18px; width: 70%; margin-bottom: 4px; }
.sk-line--short { width: 40%; }
.sk-line--full  { width: 100%; }
.sk-line--meta  { width: 30%; margin-top: 6px; }

@keyframes sk-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: 0 0; }
}
</style>
