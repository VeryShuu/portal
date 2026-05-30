<template>
  <div class="module-header">
    <div>
      <div class="branding-section__title">
        {{ title }}
      </div>
      <div class="branding-section__hint">
        {{ hint }}
      </div>
    </div>
    <div
      v-if="settingsLabel"
      class="module-header__right"
    >
      <n-button
        text
        size="small"
        @click="$emit('openSettings')"
      >
        {{ settingsLabel }} →
      </n-button>
      <n-switch
        :value="enabled"
        :loading="loading"
        @update:value="$emit('update:enabled', $event)"
      />
    </div>
    <n-switch
      v-else
      :value="enabled"
      :loading="loading"
      @update:value="$emit('update:enabled', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { NButton, NSwitch } from 'naive-ui'

defineProps<{
  title: string
  hint: string
  enabled: boolean
  loading?: boolean
  settingsLabel?: string
}>()

defineEmits<{
  (e: 'update:enabled', value: boolean): void
  (e: 'openSettings'): void
}>()
</script>

<style scoped>
@import '../../../pages/admin/admin-tabs.css';

.module-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
