<template>
  <n-drawer :show="show" placement="left" :width="240" :mask-closable="true" @update:show="$emit('update:show', $event)">
    <div class="mobile-drawer">
      <div v-if="!logoHidden" class="logo-wrap" @click="onLogoClick">
        <img v-if="logoUrl" :src="logoUrl" class="logo-img" alt="Logo" />
        <div v-else class="logo-mark">
          <span class="logo-mark__dot" />
        </div>
      </div>
      <n-menu
        :options="menuOptions"
        :value="activeKey"
        :indent="18"
        @update:value="onSelect"
      />
    </div>
  </n-drawer>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { NDrawer, NMenu, type MenuOption } from 'naive-ui'

withDefaults(
  defineProps<{
    show: boolean
    logoUrl: string | null
    logoHidden?: boolean
    menuOptions: MenuOption[]
    activeKey: string
  }>(),
  { logoHidden: false },
)

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'select', key: string): void
}>()

const router = useRouter()

function onLogoClick() {
  router.push('/')
  emit('update:show', false)
}

function onSelect(key: string) {
  emit('select', key)
  emit('update:show', false)
}
</script>

<style scoped>
.mobile-drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-surface);
  overflow-y: auto;
}
.mobile-drawer .logo-wrap {
  border-bottom: 1px solid var(--color-border);
}
.logo-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px 18px;
  cursor: pointer;
  user-select: none;
  height: var(--layout-header-height);
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
</style>
