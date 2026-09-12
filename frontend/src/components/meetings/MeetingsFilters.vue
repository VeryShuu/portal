<template>
  <div class="meetings-filters">
    <div class="meetings-filters__center">
      <div class="meetings-filters__date-row">
        <n-button
          size="small"
          circle
          @click="$emit('prev')"
        >
          <template #icon>
            <n-icon><ChevronBackOutline /></n-icon>
          </template>
        </n-button>
        <span class="meetings-filters__date-text">{{ formattedDate }}</span>
        <n-button
          size="small"
          circle
          @click="$emit('next')"
        >
          <template #icon>
            <n-icon><ChevronForwardOutline /></n-icon>
          </template>
        </n-button>
      </div>
      <span class="meetings-filters__dow">{{ formattedDow }}</span>
      <n-button
        size="small"
        @click="$emit('today')"
      >
        {{ t('meetings.today') }}
      </n-button>
    </div>
    <n-button
      v-if="auth.isAdmin"
      class="meetings-filters__settings"
      size="tiny"
      quaternary
      circle
      :title="t('admin.modules.openMeetingsSettings')"
      @click="manage.open('module')"
    >
      <template #icon>
        <n-icon :component="SettingsOutline" />
      </template>
    </n-button>

    <n-drawer
      v-if="auth.isAdmin"
      :show="manage.is('module')"
      :width="640"
      placement="right"
      :on-update:show="(v: boolean) => { if (!v) manage.close() }"
    >
      <n-drawer-content
        :title="t('admin.modules.openMeetingsSettings')"
        closable
      >
        <Suspense>
          <MeetingsModuleSettings />
        </Suspense>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDrawer, NDrawerContent, NIcon } from 'naive-ui'
import { ChevronBackOutline, ChevronForwardOutline, SettingsOutline } from '@vicons/ionicons5'
import { useManageDrawer } from '../../composables/useManageDrawer'
import { useAuthStore } from '../../stores/auth'

defineProps<{
  formattedDate: string
  formattedDow: string
}>()

defineEmits<{
  prev: []
  next: []
  today: []
}>()

const { t } = useI18n()
const auth = useAuthStore()
const manage = useManageDrawer(['module'])
const MeetingsModuleSettings = defineAsyncComponent(
  () => import('../admin/MeetingsModuleSettings.vue'),
)
</script>

<style scoped>
.meetings-filters {
  display: flex;
  justify-content: center;
  position: relative;
}
.meetings-filters__settings {
  position: absolute;
  right: 0;
  top: 0;
}
.meetings-filters__center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.meetings-filters__date-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.meetings-filters__date-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
}
.meetings-filters__dow {
  font-size: 12px;
  color: var(--color-text-muted);
  text-transform: capitalize;
}
</style>
