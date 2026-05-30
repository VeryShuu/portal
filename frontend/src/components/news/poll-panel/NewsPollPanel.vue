<template>
  <div class="u-panel poll-panel">
    <PollPanelHeader
      :show-delete="!!newsId && !!poll"
      :deleting="deleting"
      @delete="handleDelete"
    />

    <div
      v-if="!newsId"
      class="u-panel__hint"
      style="color:var(--color-warning,#f0a020)"
    >
      {{ t('news.form.saveFirst') }}
    </div>

    <PollPanelResults
      v-else-if="!poll && !showCreateForm"
      @create="initCreateForm"
    />

    <div
      v-else-if="newsId"
      class="poll-form"
    >
      <PollPanelAdmin
        :form="pollForm"
        :has-votes="hasVotes"
      />

      <PollPanelVoting
        :form="pollForm"
        :has-votes="hasVotes"
        :uploading-image="uploadingImage"
        :news-id="newsId"
        :saving="saving"
        :show-cancel-button="!poll"
        :on-image-upload="handleOptionImageUpload"
        @save="handleSave"
        @cancel="cancelCreate"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import PollPanelHeader from './PollPanelHeader.vue'
import PollPanelResults from './PollPanelResults.vue'
import PollPanelAdmin from './PollPanelAdmin.vue'
import PollPanelVoting from './PollPanelVoting.vue'
import { usePollPanelState } from './composables/usePollPanelState'

const props = defineProps<{
  newsId?: string
  hasPoll?: boolean
}>()

const { t } = useI18n()

const {
  poll,
  pollForm,
  showCreateForm,
  saving,
  deleting,
  uploadingImage,
  hasVotes,
  initCreateForm,
  cancelCreate,
  handleOptionImageUpload,
  handleSave,
  handleDelete,
} = usePollPanelState(toRef(props, 'newsId'), toRef(props, 'hasPoll'))
</script>

<style scoped>
.poll-panel {
  margin-top: 20px;
}

.poll-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 12px;
}

.u-panel__hint {
  margin-bottom: 8px;
}
</style>
