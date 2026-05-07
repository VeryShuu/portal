<template>
  <div class="empty" :class="{ 'empty--compact': compact }">
    <div class="empty__icon" aria-hidden="true">
      <slot name="icon">
        <svg v-if="variant === 'news'" viewBox="0 0 120 120" width="80" height="80">
          <rect x="18" y="28" width="84" height="72" rx="8" fill="none" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <line x1="30" y1="48" x2="90" y2="48" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <line x1="30" y1="62" x2="74" y2="62" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <line x1="30" y1="76" x2="82" y2="76" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <circle cx="90" cy="32" r="8" fill="var(--color-brand-red)"/>
        </svg>
        <svg v-else-if="variant === 'bookmark'" viewBox="0 0 120 120" width="80" height="80">
          <path d="M 40 22 L 80 22 Q 86 22 86 28 L 86 98 L 60 82 L 34 98 L 34 28 Q 34 22 40 22 Z"
            fill="none" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <circle cx="88" cy="28" r="10" fill="var(--color-brand-red)"/>
          <text x="88" y="33" font-size="14" font-weight="700" fill="#fff" text-anchor="middle">+</text>
        </svg>
        <svg v-else-if="variant === 'search'" viewBox="0 0 120 120" width="80" height="80">
          <circle cx="50" cy="50" r="28" fill="none" stroke="currentColor" stroke-width="3" opacity="0.4"/>
          <line x1="72" y1="72" x2="92" y2="92" stroke="currentColor" stroke-width="4" stroke-linecap="round" opacity="0.5"/>
          <circle cx="50" cy="50" r="6" fill="var(--color-brand-red)"/>
        </svg>
        <svg v-else-if="variant === 'file'" viewBox="0 0 120 120" width="80" height="80">
          <rect x="14" y="28" width="56" height="68" rx="5" fill="none" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <path d="M14 48h56" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <path d="M14 46V38a5 5 0 015-5h14l6 6h21a5 5 0 015 5v2" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <line x1="26" y1="62" x2="58" y2="62" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <line x1="26" y1="74" x2="50" y2="74" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <circle cx="88" cy="36" r="14" fill="var(--color-brand-red)" opacity="0.9"/>
          <path d="M88 30v8M88 40v2" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>
        </svg>
        <svg v-else-if="variant === 'photo'" viewBox="0 0 120 120" width="80" height="80">
          <rect x="12" y="28" width="96" height="68" rx="7" fill="none" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <circle cx="38" cy="50" r="9" fill="none" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <path d="M12 80l26-22 18 18 14-12 30 26" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round" opacity="0.4"/>
          <circle cx="88" cy="34" r="10" fill="var(--color-brand-red)"/>
          <path d="M84 34h8M88 30v8" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <svg v-else viewBox="0 0 120 120" width="80" height="80">
          <rect x="20" y="20" width="80" height="80" rx="10" fill="none" stroke="currentColor" stroke-width="2.5" opacity="0.4"/>
          <circle cx="60" cy="60" r="10" fill="var(--color-brand-red)"/>
        </svg>
      </slot>
    </div>
    <div class="empty__title">{{ title }}</div>
    <div v-if="description" class="empty__desc">{{ description }}</div>
    <div v-if="$slots.action" class="empty__action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  variant?: 'news' | 'bookmark' | 'search' | 'file' | 'photo' | 'default'
  title: string
  description?: string
  compact?: boolean
}>()
</script>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 40px 24px;
  color: var(--color-text-muted);
}
.empty--compact { padding: 20px 12px; }
.empty__icon {
  color: var(--color-brand-navy);
  opacity: 0.85;
  margin-bottom: 12px;
}
.empty--compact .empty__icon svg { width: 56px; height: 56px; }
.empty__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 4px;
}
.empty--compact .empty__title { font-size: 13px; }
.empty__desc {
  font-size: 13px;
  color: var(--color-text-muted);
  max-width: 320px;
}
.empty__action {
  margin-top: 14px;
}
</style>
