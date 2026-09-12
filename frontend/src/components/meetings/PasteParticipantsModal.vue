<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('meetings.participants.pasteListTitle')"
    style="width:560px;max-width:94vw"
    :mask-closable="!resolving"
    @update:show="onUpdateShow"
  >
    <div class="paste-modal">
      <!-- Этап ввода -->
      <div
        v-if="!result"
        class="paste-modal__input"
      >
        <n-input
          v-model:value="text"
          type="textarea"
          :autosize="{ minRows: 6, maxRows: 14 }"
          :maxlength="5000"
          show-count
          :placeholder="t('meetings.participants.pasteListPlaceholder')"
          :disabled="resolving"
        />
        <div class="paste-modal__hint">
          {{ t('meetings.participants.pasteListHint') }}
        </div>
      </div>

      <!-- Этап результата -->
      <div
        v-else
        class="paste-modal__result"
      >
        <div class="paste-modal__summary">
          {{ t('meetings.participants.resolvedCount', { count: resolvedCount }) }}
          <template v-if="externalCount > 0">
            · {{ t('meetings.participants.externalCount', { count: externalCount }) }}
          </template>
        </div>

        <!-- Неоднозначные ФИО → выбор кандидата -->
        <div
          v-if="result.ambiguous.length"
          class="paste-modal__section"
        >
          <div class="paste-modal__section-title">
            {{ t('meetings.participants.ambiguousTitle', { count: result.ambiguous.length }) }}
          </div>
          <div class="paste-modal__section-hint">
            {{ t('meetings.participants.ambiguousHint') }}
          </div>
          <div
            v-for="(item, idx) in result.ambiguous"
            :key="item.query"
            class="paste-modal__ambiguous"
          >
            <div class="paste-modal__ambiguous-query">
              «{{ item.query }}»
            </div>
            <n-select
              :value="ambiguousSelections[idx] ?? null"
              :options="ambiguousOptions(item)"
              :placeholder="t('meetings.participants.ambiguousHint')"
              size="small"
              @update:value="(v: string | null) => selectAmbiguous(idx, v)"
            />
          </div>
        </div>

        <!-- Нераспознанные -->
        <div
          v-if="result.unresolved.length"
          class="paste-modal__section"
        >
          <div class="paste-modal__section-title paste-modal__section-title--muted">
            {{ t('meetings.participants.unresolvedTitle', { count: result.unresolved.length }) }}
          </div>
          <div class="paste-modal__section-hint">
            {{ t('meetings.participants.unresolvedHint') }}
          </div>
          <ul class="paste-modal__unresolved">
            <li
              v-for="entry in result.unresolved"
              :key="entry"
            >
              {{ entry }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="paste-modal__footer">
        <n-button
          :disabled="resolving"
          @click="onCancel"
        >
          {{ result ? t('common.back') : t('common.cancel') }}
        </n-button>
        <n-button
          v-if="!result"
          type="primary"
          :loading="resolving"
          :disabled="!canResolve"
          @click="onResolve"
        >
          {{ t('meetings.participants.resolve') }}
        </n-button>
        <n-button
          v-else
          type="primary"
          :disabled="!canAdd"
          @click="onAdd"
        >
          {{ t('meetings.participants.addResolved', { count: toAddCount }) }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NModal, NSelect, useMessage, type SelectOption } from 'naive-ui'
import {
  resolveParticipants,
  type InvitedUser,
  type ResolveAmbiguousItem,
  type ResolveParticipantsResponse,
} from '../../api/meetings'
import { parseApiError } from '../../utils/parseApiError'

const props = defineProps<{
  show: boolean
  /** Email уже приглашённых — для дедупа на стороне модала. */
  existingEmails: Set<string>
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'add', value: InvitedUser[]): void
}>()

const { t } = useI18n()
const message = useMessage()

const text = ref('')
const resolving = ref(false)
const result = ref<ResolveParticipantsResponse | null>(null)
// Для каждого ambiguous-элемента: выбранный user_id кандидата (или null).
const ambiguousSelections = ref<(string | null)[]>([])

const canResolve = computed(() => text.value.trim().length > 0)

const externalCount = computed(
  () => result.value?.resolved.filter(u => u.source === 'external').length ?? 0,
)

/** Resolved из бэка + выбранные кандидаты ambiguous, без дубликатов с уже приглашёнными. */
const finalAddList = computed<InvitedUser[]>(() => {
  if (!result.value) return []
  const taken = new Set(props.existingEmails)
  const out: InvitedUser[] = []

  for (const u of result.value.resolved) {
    const key = u.email.toLowerCase()
    if (taken.has(key)) continue
    taken.add(key)
    out.push(u)
  }

  // Дописываем выбранных кандидатов из ambiguous (по их user_id → построить InvitedUser).
  result.value.ambiguous.forEach((item, idx) => {
    const sel = ambiguousSelections.value[idx]
    if (!sel) return
    const cand = item.candidates.find(c => c.user_id === sel)
    if (!cand) return
    const key = cand.email.toLowerCase()
    if (taken.has(key)) return
    taken.add(key)
    out.push({
      user_id: cand.user_id,
      full_name: cand.full_name,
      email: cand.email,
      source: 'keycloak',
    })
  })

  return out
})

const resolvedCount = computed(() => finalAddList.value.length)
const toAddCount = computed(() => finalAddList.value.length)
const canAdd = computed(() => toAddCount.value > 0)

function ambiguousOptions(item: ResolveAmbiguousItem): SelectOption[] {
  return item.candidates.map(c => ({
    label: `${c.full_name} (${c.email})${c.position ? ' · ' + c.position : ''}${c.department ? ' · ' + c.department : ''}`,
    value: c.user_id,
  }))
}

function selectAmbiguous(idx: number, value: string | null): void {
  ambiguousSelections.value[idx] = value
}

function reset(): void {
  text.value = ''
  result.value = null
  ambiguousSelections.value = []
  resolving.value = false
}

async function onResolve(): Promise<void> {
  // Бэк сам токенизирует (запятые/переносы/табы), но передаём по строкам для читаемости.
  const queries = text.value.split('\n')
  resolving.value = true
  try {
    const resp = await resolveParticipants(queries)
    result.value = resp
    ambiguousSelections.value = resp.ambiguous.map(() => null)
  } catch (err: unknown) {
    message.error(parseApiError(err, t, t('meetings.participants.resolveError')))
  } finally {
    resolving.value = false
  }
}

function onAdd(): void {
  const list = finalAddList.value
  if (!list.length) {
    message.info(t('meetings.participants.nothingToAdd'))
    return
  }
  emit('add', list)
  message.success(t('meetings.participants.addedToast', { count: list.length }))
  reset()
  emit('update:show', false)
}

function onCancel(): void {
  if (result.value) {
    // Из результата — назад к вводу (перередактировать список).
    result.value = null
    ambiguousSelections.value = []
    return
  }
  emit('update:show', false)
}

function onUpdateShow(value: boolean): void {
  if (!value) {
    reset()
  }
  emit('update:show', value)
}

// Сбрасываем состояние при каждом открытии.
watch(
  () => props.show,
  show => {
    if (show) reset()
  },
)
</script>

<style scoped>
.paste-modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.paste-modal__hint {
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.4;
}

.paste-modal__summary {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
  padding: 8px 12px;
  background: var(--color-bg-muted);
  border-radius: var(--radius-sm);
}

.paste-modal__result {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.paste-modal__section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.paste-modal__section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.paste-modal__section-title--muted {
  color: var(--color-text-muted);
}

.paste-modal__section-hint {
  font-size: 12px;
  color: var(--color-text-muted);
}

.paste-modal__ambiguous {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
}

.paste-modal__ambiguous-query {
  font-size: 13px;
  color: var(--color-text);
}

.paste-modal__unresolved {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: var(--color-text-muted);
}

.paste-modal__unresolved li {
  padding: 2px 0;
}

.paste-modal__footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
