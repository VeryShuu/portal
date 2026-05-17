<template>
  <div
    v-if="!variant || variant === 'news'"
    class="skeleton-card skeleton-card--news"
  >
    <div class="skeleton-card__cover" />
    <div class="skeleton-card__body">
      <div class="sk-line sk-line--title" />
      <div class="sk-line sk-line--short" />
      <div class="sk-line sk-line--full" />
      <div class="sk-line sk-line--full" />
      <div class="sk-line sk-line--meta" />
    </div>
  </div>

  <div
    v-else-if="variant === 'article' || variant === 'list'"
    class="skeleton-card"
  >
    <div class="skeleton-card__body">
      <div class="sk-line sk-line--title" />
      <div class="sk-line sk-line--short" />
      <div class="sk-line sk-line--full" />
      <div class="sk-line sk-line--full" />
      <div class="sk-line sk-line--meta" />
    </div>
  </div>

  <div
    v-else-if="variant === 'file-row'"
    class="skeleton-file-row"
  >
    <div class="sk-file-icon" />
    <div class="sk-file-name">
      <div class="sk-line" />
    </div>
    <div class="sk-file-size">
      <div class="sk-line" />
    </div>
    <div class="sk-file-date">
      <div class="sk-line" />
    </div>
    <div class="sk-file-actions">
      <div class="sk-line" />
    </div>
  </div>

  <div
    v-else-if="variant === 'folder-item'"
    class="skeleton-folder-item"
  >
    <div class="sk-folder-icon" />
    <div class="sk-line sk-line--folder" />
  </div>
</template>

<script setup lang="ts">
defineProps<{ variant?: 'news' | 'list' | 'article' | 'file-row' | 'folder-item' }>()
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

/* file-row variant */
.skeleton-file-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--color-border);
}
.skeleton-file-row:last-child { border-bottom: 0; }
.sk-file-icon {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  flex-shrink: 0;
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-bg) 37%, var(--color-bg-muted) 63%);
  background-size: 400% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
.sk-file-name { flex: 1; min-width: 0; }
.sk-file-name .sk-line { width: 60%; }
.sk-file-size { width: 64px; flex-shrink: 0; }
.sk-file-size .sk-line { width: 100%; }
.sk-file-date { width: 120px; flex-shrink: 0; }
.sk-file-date .sk-line { width: 100%; }
.sk-file-actions { width: 160px; flex-shrink: 0; }
.sk-file-actions .sk-line { width: 70%; }
.skeleton-file-row:nth-child(2n) .sk-file-name .sk-line { width: 45%; }
.skeleton-file-row:nth-child(3n) .sk-file-name .sk-line { width: 75%; }

/* folder-item variant */
.skeleton-folder-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}
.sk-folder-icon {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  flex-shrink: 0;
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-bg) 37%, var(--color-bg-muted) 63%);
  background-size: 400% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
.sk-line--folder { width: 65%; }
.skeleton-folder-item:nth-child(2) .sk-line--folder { width: 50%; }
.skeleton-folder-item:nth-child(3) .sk-line--folder { width: 78%; }
.skeleton-folder-item:nth-child(4) .sk-line--folder { width: 42%; }
.skeleton-folder-item:nth-child(5) .sk-line--folder { width: 60%; }
.skeleton-folder-item:nth-child(6) .sk-line--folder { width: 55%; }

@keyframes sk-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: 0 0; }
}
</style>
