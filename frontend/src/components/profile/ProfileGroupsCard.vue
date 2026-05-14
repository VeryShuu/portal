<template>
  <section class="profile-card">
    <header class="profile-card__head">
      <h2 class="profile-card__title">{{ t('users.profile.sections.groups') }}</h2>
    </header>
    <div v-if="loading" class="groups-loading">
      <n-spin size="small" />
    </div>
    <div v-else-if="groups.length" class="groups-list">
      <n-tag
        v-for="g in groups"
        :key="g"
        size="medium"
        :bordered="false"
        class="group-tag"
      >
        {{ g }}
      </n-tag>
    </div>
    <div v-else class="groups-empty">
      {{ t('users.profile.noGroups') }}
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NSpin, NTag } from 'naive-ui'

defineProps<{
  groups: string[]
  loading: boolean
}>()

const { t } = useI18n()
</script>

<style scoped>
.profile-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  box-shadow: var(--shadow-sm);
}
.profile-card__head {
  margin-bottom: 16px;
}
.profile-card__title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}
.groups-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.group-tag {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}
.groups-empty {
  font-size: 13px;
  color: var(--color-text-muted);
}
.groups-loading {
  display: flex;
  justify-content: flex-start;
  padding: 4px 0;
}
</style>
