<template>
  <n-dropdown :options="userMenuOptions" placement="bottom-end" @select="handleUserAction">
    <button class="user-pill" type="button">
      <n-avatar
        round
        :size="30"
        :src="auth.user?.avatar_url ?? undefined"
        color="#d8262c"
      >
        <template v-if="!auth.user?.avatar_url">{{ initials }}</template>
      </n-avatar>
      <span class="user-pill__name">{{ auth.user?.full_name }}</span>
      <n-icon size="14" class="user-pill__chev"><ChevronDownOutline /></n-icon>
    </button>
  </n-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NAvatar, NDropdown, NIcon } from 'naive-ui'
import { ChevronDownOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../../stores/auth'

const props = defineProps<{
  onAbout: () => void
}>()

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

const initials = computed(() => {
  const name = auth.user?.full_name ?? ''
  return name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()
})

const userMenuOptions = computed(() => [
  { label: t('nav.profile'), key: 'profile' },
  { type: 'divider', key: 'd1' },
  { label: t('nav.aboutPortal'), key: 'about' },
  { type: 'divider', key: 'd2' },
  { label: t('auth.logout'), key: 'logout' },
])

function handleUserAction(key: string) {
  if (key === 'logout') auth.logout()
  if (key === 'profile') router.push('/profile')
  if (key === 'about') props.onAbout()
}
</script>

<style scoped>
.user-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 4px 4px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: var(--radius-pill);
  cursor: pointer;
  font-family: inherit;
  color: #fff;
  margin-left: 8px;
  transition: background var(--t-fast);
}
.user-pill:hover {
  background: rgba(255, 255, 255, 0.16);
}
.user-pill__name {
  font-size: 13px;
  font-weight: 600;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-pill__chev {
  opacity: 0.7;
}

@media (max-width: 900px) {
  .user-pill__name { display: none; }
}
</style>
