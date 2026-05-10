<template>
  <div class="admin-wrap">
    <header class="page-head">
      <h1 class="page-head__title">{{ t('admin.title') }}</h1>
    </header>

    <n-tabs v-model:value="activeTab" type="line" animated display-directive="if">
      <n-tab-pane name="users" :tab="t('admin.tabs.users')">
        <Suspense><UsersTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane name="email" :tab="t('admin.email.tab')">
        <Suspense><EmailTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane name="system" :tab="t('admin.tabs.system')">
        <Suspense><SystemTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane name="keycloak" :tab="t('admin.tabs.keycloak')">
        <Suspense><KeycloakTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane name="user-attributes" :tab="t('admin.tabs.userAttributes')">
        <Suspense><UserAttributesTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane name="modules" :tab="t('admin.tabs.modules')">
        <Suspense><ModulesTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane name="analytics" :tab="t('admin.tabs.analytics')">
        <Suspense><AnalyticsTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane name="audit" :tab="t('admin.tabs.audit')">
        <Suspense><AuditTab /></Suspense>
      </n-tab-pane>
      <n-tab-pane name="monitoring" :tab="t('admin.tabs.monitoring')">
        <Suspense><MonitoringTab /></Suspense>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { NTabs, NTabPane } from 'naive-ui'

const { t } = useI18n()
const activeTab = ref('users')

const UsersTab = defineAsyncComponent(() => import('./admin/tabs/UsersTab.vue'))
const EmailTab = defineAsyncComponent(() => import('./admin/tabs/EmailTab.vue'))
const SystemTab = defineAsyncComponent(() => import('./admin/tabs/SystemTab.vue'))
const KeycloakTab = defineAsyncComponent(() => import('./admin/tabs/KeycloakTab.vue'))
const UserAttributesTab = defineAsyncComponent(() => import('./admin/tabs/UserAttributesTab.vue'))
const ModulesTab = defineAsyncComponent(() => import('./admin/tabs/ModulesTab.vue'))
const AnalyticsTab = defineAsyncComponent(() => import('./admin/tabs/AnalyticsTab.vue'))
const AuditTab = defineAsyncComponent(() => import('./admin/tabs/AuditTab.vue'))
const MonitoringTab = defineAsyncComponent(() => import('./admin/tabs/MonitoringTab.vue'))
</script>

<style scoped>
.admin-wrap {
  max-width: 1280px;
  margin: 0 auto;
}

.page-head {
  margin-bottom: 20px;
}

.page-head__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text);
}
</style>
