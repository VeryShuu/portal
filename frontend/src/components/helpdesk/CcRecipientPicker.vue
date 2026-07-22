<template>
  <div class="cc-picker">
    <div
      v-if="modelValue.length"
      class="cc-picker__invited"
    >
      <div class="cc-picker__invited-label">
        {{ t('helpdesk.cc.invited', { count: modelValue.length }) }}
      </div>
      <div class="cc-picker__tags">
        <div
          v-for="r in modelValue"
          :key="r.email"
          class="cc-tag"
        >
          <span
            v-if="r.source === 'external'"
            class="cc-tag__badge"
          >{{ t('helpdesk.cc.externalBadge') }}</span>
          <span
            v-else
            class="cc-tag__name"
          >{{ r.name || r.email }}</span>
          <span class="cc-tag__email">({{ r.email }})</span>
          <button
            class="cc-tag__remove"
            type="button"
            :disabled="disabled"
            :aria-label="t('helpdesk.cc.remove')"
            @click="remove(r.email)"
          >
            ×
          </button>
        </div>
      </div>
    </div>

    <n-select
      multiple
      filterable
      remote
      clear-filter-after-select
      :value="[]"
      :options="dropdownOptions"
      :loading="searching"
      :disabled="disabled"
      :placeholder="t('helpdesk.cc.searchPlaceholder')"
      :render-label="renderLabel"
      @search="onSearch"
      @update:value="onSelect"
    />
    <div
      v-if="errorText"
      class="cc-picker__error"
    >
      {{ errorText }}
    </div>
    <div class="cc-picker__hint">
      {{ t('helpdesk.cc.searchHint') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSelect, type SelectOption } from 'naive-ui'
import { searchHelpdeskUsers, type HelpdeskUserOption } from '../../api/helpdesk'
import { useDebounceFn } from '../../composables/useDebounceFn'
import { parseApiError } from '../../utils/parseApiError'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const EXTERNAL_PREFIX = 'ext:'

/**
 * CC-получатель в форме ответа агента. ``source`` отличает пользователя
 * справочника (есть ФИО) от произвольного email (бейдж «внешний»). На submit
 * ``TicketReplyForm`` мапит массив в ``string[]`` email'ов (контракт бэка).
 */
export interface CcRecipient {
  email: string
  name: string | null
  source: 'directory' | 'external'
}

const props = defineProps<{
  modelValue: CcRecipient[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: CcRecipient[]): void
}>()

const { t } = useI18n()

const searchResults = ref<HelpdeskUserOption[]>([])
const searching = ref(false)
const errorText = ref<string | null>(null)
const currentQuery = ref('')

const selectedEmails = computed(
  () => new Set(props.modelValue.map((r) => r.email.toLowerCase())),
)

const directoryOptions = computed<SelectOption[]>(() =>
  searchResults.value
    .filter((u) => !selectedEmails.value.has(u.email.toLowerCase()))
    .map((u) => ({
      label: `${u.full_name} (${u.email})`,
      value: u.user_id,
    })),
)

// Synthetic «external»-опция: появляется, когда введён валидный email, которого
// нет в справочнике и среди выбранных. Позволяет добавить в CC произвольный адрес.
const externalOption = computed<SelectOption | null>(() => {
  const email = currentQuery.value.trim().toLowerCase()
  if (searching.value || !EMAIL_RE.test(email)) return null
  if (selectedEmails.value.has(email)) return null
  if (searchResults.value.some((u) => u.email.toLowerCase() === email)) return null
  return { label: email, value: `${EXTERNAL_PREFIX}${email}` }
})

const dropdownOptions = computed<SelectOption[]>(() =>
  externalOption.value
    ? [...directoryOptions.value, externalOption.value]
    : directoryOptions.value,
)

function renderLabel(option: SelectOption) {
  const value = String(option.value ?? '')
  if (!value.startsWith(EXTERNAL_PREFIX)) return option.label as string
  return h('div', { class: 'cc-external' }, [
    h('span', { class: 'cc-tag__badge' }, t('helpdesk.cc.externalBadge')),
    h('span', { class: 'cc-external__email' }, String(option.label)),
  ])
}

const doSearch = useDebounceFn(async (q: string) => {
  const trimmed = q.trim()
  if (trimmed.length < 3) {
    searchResults.value = []
    errorText.value = null
    return
  }
  searching.value = true
  errorText.value = null
  try {
    searchResults.value = await searchHelpdeskUsers(trimmed)
  } catch (e: unknown) {
    errorText.value = parseApiError(e, t, t('helpdesk.cc.searchError'))
    searchResults.value = []
  } finally {
    searching.value = false
  }
}, 300)

function onSearch(q: string) {
  currentQuery.value = q
  doSearch(q)
}

function buildExternal(email: string): CcRecipient {
  return { email, name: null, source: 'external' }
}

function onSelect(values: string[]) {
  if (!values.length) return
  const added: CcRecipient[] = []
  const taken = new Set(selectedEmails.value)
  for (const value of values) {
    let candidate: CcRecipient | null = null
    if (value.startsWith(EXTERNAL_PREFIX)) {
      candidate = buildExternal(value.slice(EXTERNAL_PREFIX.length))
    } else {
      const found = searchResults.value.find((u) => u.user_id === value)
      if (found && !taken.has(found.email.toLowerCase())) {
        candidate = { email: found.email, name: found.full_name, source: 'directory' }
      }
    }
    if (candidate && !taken.has(candidate.email.toLowerCase())) {
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

function remove(email: string) {
  if (props.disabled) return
  emit(
    'update:modelValue',
    props.modelValue.filter((r) => r.email !== email),
  )
}
</script>

<style scoped>
.cc-picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 240px;
}

.cc-picker__invited-label {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}

.cc-picker__tags {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cc-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: var(--color-bg-muted);
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.cc-tag__name {
  font-weight: 500;
  color: var(--color-text);
}

.cc-tag__badge {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--primary-color, #2080f0);
  color: #fff;
}

.cc-tag__email {
  color: var(--color-text-muted);
  flex: 1;
}

.cc-tag__remove {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-text-muted);
  font-size: 16px;
  line-height: 1;
  padding: 0 2px;
}

.cc-tag__remove:hover:not(:disabled) {
  color: var(--error-color);
}

.cc-tag__remove:focus-visible {
  outline: 2px solid var(--primary-color, #2080f0);
  outline-offset: 1px;
  border-radius: 2px;
}

.cc-tag__remove:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cc-external {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cc-external__email {
  color: var(--color-text);
}

.cc-picker__hint {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

.cc-picker__error {
  font-size: 12px;
  color: var(--error-color, #c0392b);
  margin-top: 2px;
}
</style>
