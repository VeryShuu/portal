<template>
  <div class="participant-picker">
    <div
      v-if="modelValue.length"
      class="invited-section"
    >
      <div class="invited-label">
        {{ t('meetings.participants.invited', { count: modelValue.length }) }}
      </div>
      <div class="participant-tags">
        <div
          v-for="u in modelValue"
          :key="u.user_id"
          class="participant-tag"
        >
          <span class="participant-tag__name">{{ u.full_name }}</span>
          <span class="participant-tag__email">({{ u.email }})</span>
          <button
            class="participant-tag__remove"
            type="button"
            :aria-label="t('common.remove')"
            @click="remove(u.user_id)"
          >
            ×
          </button>
        </div>
      </div>
    </div>

    <div class="add-section">
      <div class="add-label">
        {{ t('meetings.participants.addParticipants') }}
      </div>
      <n-select
        multiple
        filterable
        remote
        clear-filter-after-select
        :value="[]"
        :options="dropdownOptions"
        :loading="searching"
        :placeholder="t('meetings.participants.searchPlaceholder')"
        @search="onSearch"
        @update:value="onSelect"
      />
      <div
        v-if="errorText"
        class="search-error"
      >
        {{ errorText }}
      </div>
      <div class="search-hint">
        {{ t('meetings.participants.searchHint') }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSelect } from 'naive-ui'
import { searchParticipants, type InvitedUser } from '../../api/meetings'
import { useDebounceFn } from '../../composables/useDebounceFn'

const props = defineProps<{
  modelValue: InvitedUser[]
  minChars?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: InvitedUser[]): void
}>()

const { t } = useI18n()
const minChars = computed(() => props.minChars ?? 3)

const searchResults = ref<InvitedUser[]>([])
const searching = ref(false)
const errorText = ref<string | null>(null)

const dropdownOptions = computed(() =>
  searchResults.value
    .filter(u => !props.modelValue.some(m => m.user_id === u.user_id))
    .map(u => ({
      label: `${u.full_name} (${u.email})`,
      value: u.user_id,
    })),
)

const doSearch = useDebounceFn(async (q: string) => {
  const trimmed = q.trim()
  if (trimmed.length < minChars.value) {
    searchResults.value = []
    errorText.value = null
    return
  }
  searching.value = true
  errorText.value = null
  try {
    searchResults.value = await searchParticipants(trimmed)
  } catch (e: unknown) {
    const err = e as { data?: { detail?: string } }
    errorText.value = err?.data?.detail ?? t('meetings.participants.searchError')
    searchResults.value = []
  } finally {
    searching.value = false
  }
}, 300)

function onSearch(q: string) {
  doSearch(q)
}

function onSelect(userIds: string[]) {
  if (!userIds.length) return
  const added: InvitedUser[] = []
  for (const id of userIds) {
    const found = searchResults.value.find(u => u.user_id === id)
    if (found && found.email && !props.modelValue.some(m => m.user_id === id)) {
      added.push(found)
    }
  }
  if (added.length) {
    emit('update:modelValue', [...props.modelValue, ...added])
  }
  searchResults.value = []
}

function remove(userId: string) {
  emit('update:modelValue', props.modelValue.filter(u => u.user_id !== userId))
}
</script>

<style scoped>
.participant-picker {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.invited-label {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}

.participant-tags {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.participant-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: var(--color-bg-muted);
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.participant-tag__name {
  font-weight: 500;
  color: var(--color-text);
}

.participant-tag__email {
  color: var(--color-text-muted);
  flex: 1;
}

.participant-tag__remove {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text-muted);
  font-size: 16px;
  line-height: 1;
  padding: 0 2px;
}

.participant-tag__remove:hover {
  color: var(--error-color);
}

.participant-tag__remove:focus-visible {
  outline: 2px solid var(--primary-color, #2080f0);
  outline-offset: 1px;
  border-radius: 2px;
}

.add-label {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}

.search-hint {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 4px;
}

.search-error {
  font-size: 12px;
  color: var(--error-color, #c0392b);
  margin-top: 4px;
}
</style>
