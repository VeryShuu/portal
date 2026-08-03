<template>
  <div class="branding-wrap">
    <!-- Секция: агенты поддержки -->
    <div class="helpdesk-section">
      <div class="branding-section__title">
        {{ t('admin.helpdesk.agents.title') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.helpdesk.agents.hint') }}
      </div>
      <HelpdeskAgentsManager />
    </div>

    <!-- Секция: mailbox-настройки -->
    <div class="helpdesk-section">
      <div class="branding-section__title">
        {{ t('admin.helpdesk.mailbox.title') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.helpdesk.mailbox.hint') }}
      </div>
      <HelpdeskMailboxSettings />
    </div>

    <!-- Секция: MAX-мессенджер (уведомления о новых заявках в общий чат) -->
    <div class="helpdesk-section">
      <div class="branding-section__title">
        {{ t('admin.helpdesk.max.title') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.helpdesk.max.hint') }}
      </div>
      <HelpdeskMaxBotSettings />
    </div>

    <!-- Секция: ежедневная сводка заявок (расписание) -->
    <div class="helpdesk-section">
      <div class="branding-section__title">
        {{ t('admin.helpdesk.digest.title') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.helpdesk.digest.sectionHint') }}
      </div>
      <HelpdeskDigestSettings />
    </div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const HelpdeskAgentsManager = defineAsyncComponent(
  () => import('../../../components/admin/HelpdeskAgentsManager.vue'),
)
const HelpdeskMailboxSettings = defineAsyncComponent(
  () => import('../../../components/admin/HelpdeskMailboxSettings.vue'),
)
const HelpdeskMaxBotSettings = defineAsyncComponent(
  () => import('../../../components/admin/HelpdeskMaxBotSettings.vue'),
)
const HelpdeskDigestSettings = defineAsyncComponent(
  () => import('../../../components/admin/HelpdeskDigestSettings.vue'),
)
</script>

<style scoped>
.helpdesk-section {
  margin-bottom: 32px;
}
.branding-section__title {
  font-weight: 600;
  margin-bottom: 4px;
}
.branding-section__hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 16px;
}
</style>
