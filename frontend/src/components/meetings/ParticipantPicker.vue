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
          <span
            v-if="u.source === 'external'"
            class="participant-tag__badge"
          >{{ t('meetings.participants.externalBadge') }}</span>
          <span
            v-else
            class="participant-tag__name"
          >{{ u.full_name }}</span>
          <span class="participant-tag__email">({{ u.email }})</span>
          <span
            v-if="u.absence"
            class="participant-tag__presence"
            :class="presenceClass(u.absence)"
          >{{ presenceLabel(u.absence) }}</span>
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
        :render-label="renderLabel"
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
      <n-button
        class="paste-list-btn"
        size="small"
        tertiary
        @click="pasteShow = true"
      >
        {{ t('meetings.participants.pasteList') }}
      </n-button>
    </div>

    <PasteParticipantsModal
      v-model:show="pasteShow"
      :existing-emails="existingEmails"
      @add="onBulkAdd"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NSelect, type SelectOption } from 'naive-ui'
import { searchParticipants, type InvitedUser } from '../../api/meetings'
import { useDebounceFn } from '../../composables/useDebounceFn'
import { usePresenceLabel } from '../../composables/usePresenceLabel'
import { parseApiError } from '../../utils/parseApiError'
import PasteParticipantsModal from './PasteParticipantsModal.vue'

// Whitelist разрешённых символов (как в backend/app/schemas/user._EMAIL_RE) —
// версия [^\s@]+ уязвима к ReDoS на специальном вводе.
const EMAIL_RE = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,63}$/
const EXTERNAL_PREFIX = 'ext:'

const props = defineProps<{
  modelValue: InvitedUser[]
  minChars?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: InvitedUser[]): void
}>()

const { t } = useI18n()
const { presenceLabel, presenceClass } = usePresenceLabel()
const minChars = computed(() => props.minChars ?? 3)

const searchResults = ref<InvitedUser[]>([])
const searching = ref(false)
const errorText = ref<string | null>(null)
const currentQuery = ref('')
const pasteShow = ref(false)

const existingEmails = computed(
  () => new Set(props.modelValue.map(m => m.email.toLowerCase())),
)

const employeeOptions = computed<SelectOption[]>(() =>
  searchResults.value
    .filter(u => !props.modelValue.some(m => m.user_id === u.user_id))
    .filter(u => !existingEmails.value.has(u.email.toLowerCase()))
    .map(u => ({
      label: `${u.full_name} (${u.email})`,
      value: u.user_id,
    })),
)

const externalOption = computed<SelectOption | null>(() => {
  const email = currentQuery.value.trim().toLowerCase()
  if (searching.value || !EMAIL_RE.test(email)) return null
  if (existingEmails.value.has(email)) return null
  if (searchResults.value.some(u => u.email.toLowerCase() === email)) return null
  return { label: email, value: `${EXTERNAL_PREFIX}${email}` }
})

const dropdownOptions = computed<SelectOption[]>(() =>
  externalOption.value
    ? [...employeeOptions.value, externalOption.value]
    : employeeOptions.value,
)

function renderLabel(option: SelectOption) {
  const value = String(option.value ?? '')
  if (!value.startsWith(EXTERNAL_PREFIX)) return option.label as string
  return h('div', { class: 'external-option' }, [
    h('span', { class: 'participant-tag__badge' }, t('meetings.participants.externalBadge')),
    h('span', { class: 'external-option__email' }, String(option.label)),
  ])
}

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
    errorText.value = parseApiError(e, t, t('meetings.participants.searchError'))
    searchResults.value = []
  } finally {
    searching.value = false
  }
}, 300)

function onSearch(q: string) {
  currentQuery.value = q
  doSearch(q)
}

function buildExternal(email: string): InvitedUser {
  return {
    user_id: `${EXTERNAL_PREFIX}${email}`,
    full_name: email,
    email,
    source: 'external',
  }
}

function onSelect(values: string[]) {
  if (!values.length) return
  const added: InvitedUser[] = []
  const taken = new Set(existingEmails.value)
  for (const value of values) {
    let candidate: InvitedUser | null = null
    if (value.startsWith(EXTERNAL_PREFIX)) {
      candidate = buildExternal(value.slice(EXTERNAL_PREFIX.length))
    } else {
      const found = searchResults.value.find(u => u.user_id === value)
      if (found && found.email && !props.modelValue.some(m => m.user_id === value)) {
        candidate = { ...found, source: 'keycloak' }
      }
    }
    if (candidate && candidate.email && !taken.has(candidate.email.toLowerCase())) {
      added.push(candidate)
      taken.add(candidate.email.toLowerCase())
    }
  }
  if (added.length) {
    emit('update:modelValue', [...props.modelValue, ...added])
  }
  searchResults.value = []
  currentQuery.value = ''
}

function remove(userId: string) {
  emit('update:modelValue', props.modelValue.filter(u => u.user_id !== userId))
}

function onBulkAdd(added: InvitedUser[]): void {
  // Дедуп по email (модал уже отфильтровал существующих, но подстрахуемся).
  const taken = new Set(existingEmails.value)
  const fresh = added.filter(u => {
    const key = u.email.toLowerCase()
    if (taken.has(key)) return false
    taken.add(key)
    return true
  })
  if (fresh.length) {
    emit('update:modelValue', [...props.modelValue, ...fresh])
  }
  pasteShow.value = false
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

.participant-tag__badge {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--primary-color, #2080f0);
  color: #fff;
}

.external-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.external-option__email {
  color: var(--color-text);
}

/* Информационная подпись отсутствия участника (отпуск/болезнь/командировка).
 * Повторяет формат справочника (StaffRow.vue): мелкая цветная пилюля. */
.participant-tag__presence {
  flex: none;
  margin-left: auto;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 999px;
  color: var(--color-text-muted);
  background: rgba(0, 0, 0, 0.05);
}
.participant-tag__presence.presence--vacation {
  color: var(--presence-ring-vacation);
  background: rgba(245, 158, 11, 0.12);
}
.participant-tag__presence.presence--sick {
  color: var(--presence-ring-sick);
  background: rgba(190, 18, 60, 0.1);
}
.participant-tag__presence.presence--business_trip {
  color: var(--presence-ring-business_trip);
  background: rgba(139, 92, 246, 0.12);
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

.paste-list-btn {
  align-self: flex-start;
  margin-top: 6px;
}

.search-error {
  font-size: 12px;
  color: var(--error-color, #c0392b);
  margin-top: 4px;
}
</style>
