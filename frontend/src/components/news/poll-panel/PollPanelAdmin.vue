<template>
  <div>
    <div class="poll-form__settings-grid">
      <n-form-item :label="t('news.poll.editor.resultsVisibility')">
        <n-select
          v-model:value="form.results_visibility"
          :options="visibilityOptions"
          :disabled="hasVotes"
        />
      </n-form-item>

      <n-form-item :label="t('news.poll.editor.closesAt')">
        <n-date-picker
          v-model:value="closesAtMs"
          type="datetime"
          clearable
          style="width: 100%"
        />
      </n-form-item>
    </div>

    <div class="poll-form__checkboxes">
      <n-checkbox
        v-model:checked="form.is_anonymous"
        :disabled="hasVotes"
      >
        {{ t('news.poll.editor.anonymous') }}
      </n-checkbox>
      <n-checkbox
        v-model:checked="form.allow_revote"
        :disabled="hasVotes"
      >
        {{ t('news.poll.editor.allowRevote') }}
      </n-checkbox>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NFormItem, NSelect, NDatePicker, NCheckbox } from 'naive-ui'
import type { PollForm } from './composables/usePollPanelState'

const props = defineProps<{
  form: PollForm
  hasVotes: boolean
}>()

const { t } = useI18n()

const closesAtMs = computed({
  get: () => props.form.closes_at ? new Date(props.form.closes_at).getTime() : null,
  set: (ms: number | null) => {
    props.form.closes_at = ms ? new Date(ms).toISOString() : null
  },
})

const visibilityOptions = computed(() => [
  { label: t('news.poll.editor.visibility.always'), value: 'always' },
  { label: t('news.poll.editor.visibility.after_vote'), value: 'after_vote' },
  { label: t('news.poll.editor.visibility.after_close'), value: 'after_close' },
  { label: t('news.poll.editor.visibility.only_admin_editor'), value: 'only_admin_editor' },
])
</script>

<style scoped>
.poll-form__settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.poll-form__checkboxes {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 16px;
}

@media (max-width: 600px) {
  .poll-form__settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
