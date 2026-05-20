<template>
  <div class="admin-wrap">
    <header class="page-head">
      <h1 class="u-page-head__title">
        {{ t('admin.title') }}
      </h1>
    </header>

    <n-tabs
      v-model:value="activeGroup"
      type="segment"
      size="medium"
      class="admin-groups"
    >
      <n-tab-pane
        v-for="g in GROUPS"
        :key="g.key"
        :name="g.key"
        :tab="t(`admin.groups.${g.key}`)"
      />
    </n-tabs>

    <n-tabs
      v-model:value="activeTab"
      type="line"
      animated
      display-directive="if"
      class="admin-subtabs"
    >
      <n-tab-pane
        v-for="tab in currentTabs"
        :key="tab.name"
        :name="tab.name"
        :tab="t(tab.label)"
      >
        <Suspense>
          <component :is="tab.component" />
        </Suspense>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NTabs, NTabPane } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const UsersTab = defineAsyncComponent(() => import('./admin/tabs/UsersTab.vue'))
const EmailTab = defineAsyncComponent(() => import('./admin/tabs/EmailTab.vue'))
const EmailOutboxTab = defineAsyncComponent(() => import('./admin/tabs/EmailOutboxTab.vue'))
const SystemTab = defineAsyncComponent(() => import('./admin/tabs/SystemTab.vue'))
const KeycloakTab = defineAsyncComponent(() => import('./admin/tabs/KeycloakTab.vue'))
const UserAttributesTab = defineAsyncComponent(() => import('./admin/tabs/UserAttributesTab.vue'))
const ModulesTab = defineAsyncComponent(() => import('./admin/tabs/ModulesTab.vue'))
const BrandingTab = defineAsyncComponent(() => import('./admin/tabs/BrandingTab.vue'))
const AnalyticsTab = defineAsyncComponent(() => import('./admin/tabs/AnalyticsTab.vue'))
const AuditTab = defineAsyncComponent(() => import('./admin/tabs/AuditTab.vue'))
const MonitoringTab = defineAsyncComponent(() => import('./admin/tabs/MonitoringTab.vue'))
const FeedbackTab = defineAsyncComponent(() => import('./admin/tabs/FeedbackTab.vue'))

type TabDef = { name: string; label: string; component: ReturnType<typeof defineAsyncComponent> }
type GroupDef = { key: string; tabs: TabDef[] }

const GROUPS: GroupDef[] = [
  {
    key: 'access',
    tabs: [
      { name: 'users', label: 'admin.tabs.users', component: UsersTab },
      { name: 'keycloak', label: 'admin.tabs.keycloak', component: KeycloakTab },
      { name: 'user-attributes', label: 'admin.tabs.userAttributes', component: UserAttributesTab },
    ],
  },
  {
    key: 'email',
    tabs: [
      { name: 'email', label: 'admin.tabs.email', component: EmailTab },
      { name: 'email-outbox', label: 'admin.tabs.emailOutbox', component: EmailOutboxTab },
    ],
  },
  {
    key: 'system',
    tabs: [
      { name: 'system', label: 'admin.tabs.system', component: SystemTab },
      { name: 'branding', label: 'admin.tabs.branding', component: BrandingTab },
      { name: 'modules', label: 'admin.tabs.modules', component: ModulesTab },
      { name: 'monitoring', label: 'admin.tabs.monitoring', component: MonitoringTab },
    ],
  },
  {
    key: 'logs',
    tabs: [
      { name: 'analytics', label: 'admin.tabs.analytics', component: AnalyticsTab },
      { name: 'audit', label: 'admin.tabs.audit', component: AuditTab },
      { name: 'feedback', label: 'feedback.adminTab', component: FeedbackTab },
    ],
  },
]

const TAB_TO_GROUP: Record<string, string> = GROUPS.reduce((acc, g) => {
  for (const tab of g.tabs) acc[tab.name] = g.key
  return acc
}, {} as Record<string, string>)

const VALID_TABS = Object.keys(TAB_TO_GROUP)

function readTabFromQuery(): string {
  const q = route.query.tab
  if (typeof q === 'string' && VALID_TABS.includes(q)) return q
  return 'users'
}

const activeTab = ref(readTabFromQuery())
const activeGroup = ref(TAB_TO_GROUP[activeTab.value] ?? 'access')

const currentTabs = computed(() => GROUPS.find((g) => g.key === activeGroup.value)?.tabs ?? [])

watch(activeGroup, (g) => {
  const tabs = GROUPS.find((x) => x.key === g)?.tabs ?? []
  if (!tabs.some((tab) => tab.name === activeTab.value)) {
    if (tabs[0]) activeTab.value = tabs[0].name
  }
})

watch(activeTab, (val) => {
  const group = TAB_TO_GROUP[val]
  if (group && group !== activeGroup.value) activeGroup.value = group
  if (route.query.tab !== val) {
    router.replace({ query: { ...route.query, tab: val } })
  }
})

watch(() => route.query.tab, (val) => {
  if (typeof val === 'string' && val !== activeTab.value && VALID_TABS.includes(val)) {
    activeTab.value = val
  }
})
</script>

<style scoped>
.admin-wrap {
  max-width: 1280px;
  margin: 0 auto;
}

.page-head {
  margin-bottom: 20px;
}

.admin-groups {
  margin-bottom: 12px;
}

.admin-subtabs {
  margin-top: 4px;
}
</style>
