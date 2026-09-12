<template>
  <div class="page learning-admin-page">
    <header class="page-header">
      <div>
        <h1 class="page-title">
          {{ t('learning.admin.title') }}
        </h1>
        <p class="page-subtitle">
          {{ t('learning.admin.subtitle') }}
        </p>
      </div>
    </header>

    <n-tabs
      :value="activeTab"
      type="line"
      animated
      @update:value="setTab"
    >
      <n-tab name="courses">
        {{ t('learning.admin.tabs.courses') }}
      </n-tab>
      <n-tab name="accounts">
        {{ t('learning.admin.tabs.accounts') }}
      </n-tab>
      <n-tab name="categories">
        {{ t('learning.admin.tabs.categories') }}
      </n-tab>
      <n-tab
        v-if="auth.isAdmin"
        name="methodists"
      >
        {{ t('learning.admin.tabs.methodists') }}
      </n-tab>
    </n-tabs>

    <!-- Ревью 2026-08-30: v-if вместо v-show — невидимая вкладка не должна
         запускать запросы; state вкладок живёт в ?tab=, поэтому remount безопасен -->
    <CoursesTab v-if="activeTab === 'courses'" />
    <AccountsTab v-else-if="activeTab === 'accounts'" />
    <CategoriesTab v-else-if="activeTab === 'categories'" />
    <MethodistsTab v-if="auth.isAdmin && activeTab === 'methodists'" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NTabs, NTab } from 'naive-ui'
import CoursesTab from '../../components/learning/CoursesTab.vue'
import AccountsTab from '../../components/learning/AccountsTab.vue'
import CategoriesTab from '../../components/learning/CategoriesTab.vue'
import MethodistsTab from '../../components/learning/MethodistsTab.vue'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const auth = useAuthStore()

const ADMIN_TABS = ['courses', 'accounts', 'categories', 'methodists'] as const

const activeTab = computed(() => {
  const tab = route.query.tab
  if (typeof tab === 'string' && ADMIN_TABS.includes(tab as (typeof ADMIN_TABS)[number])) {
    if (tab === 'methodists' && !auth.isAdmin) return 'courses'
    return tab
  }
  return 'courses'
})

function setTab(tab: string | number) {
  router.replace({ query: { ...route.query, tab: String(tab) } })
}
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.page-subtitle {
  margin: 4px 0 0;
  color: var(--text-secondary, #888);
}
</style>
