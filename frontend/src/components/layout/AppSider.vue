<template>
  <n-layout-sider
    bordered
    collapse-mode="width"
    :collapsed-width="64"
    :width="240"
    :collapsed="collapsed"
    show-trigger="bar"
    class="app-sider"
    :class="{ 'app-sider--collapsed': collapsed }"
    @collapse="$emit('update:collapsed', true)"
    @expand="$emit('update:collapsed', false)"
  >
    <div
      v-if="!logoHidden"
      class="logo-wrap"
      role="button"
      tabindex="0"
      @click="router.push('/')"
      @keydown.enter="router.push('/')"
    >
      <img
        v-if="logoUrl"
        :src="logoUrl"
        class="logo-img"
        alt="Logo"
      >
      <div
        v-else
        class="logo-mark"
      >
        <span class="logo-mark__dot" />
      </div>
    </div>

    <n-menu
      :collapsed="collapsed"
      :collapsed-width="64"
      :collapsed-icon-size="22"
      :options="menuOptions"
      :value="activeKey"
      :indent="18"
      @update:value="(key: string) => $emit('select', key)"
    />

    <div class="sider-footer" />
  </n-layout-sider>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { NLayoutSider, NMenu, type MenuOption } from 'naive-ui'

withDefaults(
  defineProps<{
    collapsed: boolean
    logoUrl: string | null
    logoHidden?: boolean
    menuOptions: MenuOption[]
    activeKey: string
  }>(),
  { logoHidden: false },
)

defineEmits<{
  (e: 'update:collapsed', value: boolean): void
  (e: 'select', key: string): void
}>()

const router = useRouter()
</script>

<style scoped>
.app-sider {
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
}
.app-sider :deep(.n-layout-sider-scroll-container) {
  display: flex;
  flex-direction: column;
}
.logo-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px 18px;
  cursor: pointer;
  user-select: none;
  height: var(--layout-header-height);
  border-bottom: 1px solid var(--color-border);
  box-sizing: border-box;
  flex-shrink: 0;
}
.logo-img {
  max-height: 40px;
  max-width: 180px;
  object-fit: contain;
}
.logo-mark {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--gradient-hero);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  box-shadow: var(--shadow-sm);
}
.logo-mark__dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-brand-red);
  box-shadow: 0 0 0 3px rgba(216, 38, 44, 0.18);
}

:deep(.menu-group-label) {
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-size: 10px;
  font-weight: 700;
  color: var(--color-text-subtle);
}

.app-sider--collapsed :deep(.n-menu-item-group-title) {
  display: none;
}

.app-sider :deep(.n-menu-item-content:not(.n-menu-item-content--selected):hover) {
  background: var(--color-bg-muted) !important;
}

.app-sider :deep(.n-menu-item-content--selected)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--color-brand-red);
  transition: none !important;
}
.app-sider :deep(.n-menu-item-content) {
  position: relative;
}
.app-sider :deep(.n-menu-item-content)::before {
  transition: none !important;
}

.sider-footer {
  margin-top: auto;
  border-top: 1px solid var(--color-border);
  padding: 12px;
}
</style>
