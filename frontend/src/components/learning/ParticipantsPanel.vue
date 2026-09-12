<template>
  <section>
    <div class="panel-actions">
      <n-button
        size="small"
        quaternary
        @click="downloadExport"
      >
        {{ t('learning.participants.export') }}
      </n-button>
      <n-button
        size="small"
        type="primary"
        :disabled="isDraft"
        @click="openEnroll"
      >
        <template #icon>
          <n-icon><PersonAddOutline /></n-icon>
        </template>
        {{ t('learning.participants.enroll') }}
      </n-button>
    </div>
    <p
      v-if="isDraft"
      class="panel-draft-hint"
    >
      {{ t('learning.participants.enrollDraftHint') }}
    </p>

    <n-data-table
      :columns="columns"
      :data="rows"
      :loading="query.isLoading.value"
      :row-key="(r: LearningParticipantRow) => r.id"
      :bordered="false"
      striped
    />

    <n-modal
      class="learning-participant-modal"
      v-model:show="enrollOpen"
      preset="card"
      :title="t('learning.participants.enrollTitle')"
      style="max-width: 520px"
    >
      <n-radio-group
        v-model:value="enrollKind"
        style="margin-bottom: 12px"
      >
        <n-radio value="staff">
          {{ t('learning.participants.kindStaff') }}
        </n-radio>
        <n-radio value="external">
          {{ t('learning.participants.kindExternal') }}
        </n-radio>
      </n-radio-group>

      <n-select
        v-if="enrollKind === 'staff'"
        v-model:value="staffIds"
        multiple
        filterable
        clearable
        remote
        :options="staffOptions"
        :loading="staffSearching"
        :placeholder="t('learning.participants.searchStaff')"
        @search="searchStaff"
      />
      <n-select
        v-else
        v-model:value="accountId"
        filterable
        clearable
        remote
        :options="accountOptions"
        :loading="accountsSearching"
        :placeholder="t('learning.participants.pickAccount')"
        @search="searchAccounts"
      />

      <template #footer>
        <div class="modal-actions">
          <n-button @click="enrollOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="enrollKind === 'staff' ? bulkEnrollMut.isPending.value : enrollMut.isPending.value"
            @click="submitEnroll"
          >
            {{ t('learning.participants.enroll') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </section>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDataTable,
  NIcon,
  NModal,
  NPopconfirm,
  NRadio,
  NRadioGroup,
  NSelect,
  NTag,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { PersonAddOutline } from '@vicons/ionicons5'
import {
  useAdminProgressQuery,
  useBulkEnrollMutation,
  useEnrollParticipantMutation,
  useUnenrollParticipantMutation,
} from '../../queries/learning'
import { fetchUsers } from '../../api/users'
import {
  exportProgressBlob,
  fetchParticipantCertificateBlob,
  fetchLearningAccounts,
} from '../../api/learning'
import type { LearningParticipantRow } from '../../api/learning'
import { downloadBlob } from '../../utils/download'
import { parseApiError } from '../../utils/parseApiError'
import { useMutationErrorToasts } from '../../composables/useMutationErrorToasts'
import { useRemoteSearch } from '../../composables/useRemoteSearch'
import ParticipantItemsDetail from './ParticipantItemsDetail.vue'

const props = defineProps<{ courseId: string; courseStatus?: string | null }>()
const { t } = useI18n()
const message = useMessage()

// Зачисление только на опубликованный курс: черновик невидим участнику
// (бэкенд отвечает 409, прод-кейс 2026-09-02) — блокируем кнопку заранее.
const isDraft = computed(() => (props.courseStatus ?? 'published') !== 'published')

const query = useAdminProgressQuery(computed(() => props.courseId))
const rows = computed<LearningParticipantRow[]>(() => query.data.value?.participants ?? [])

watch(() => query.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })

const enrollMut = useEnrollParticipantMutation()
const bulkEnrollMut = useBulkEnrollMutation()
const unenrollMut = useUnenrollParticipantMutation()
useMutationErrorToasts([enrollMut.error, bulkEnrollMut.error, unenrollMut.error], (text) => message.error(text), t)
// Ревью 2026-08-30: у bulk-мутации не было error-watch — сетевая ошибка
// падала молча, а catch ссылался на «watch, который покажет».

const enrollOpen = ref(false)
const enrollKind = ref<'staff' | 'external'>('staff')
// групповое зачисление (этап 2): сотрудники выбираются списком
const staffIds = ref<string[]>([])
const accountId = ref<string | null>(null)

async function downloadExport() {
  try {
    const blob = await exportProgressBlob(props.courseId)
    downloadBlob(blob, `learning-progress-${props.courseId}.xlsx`)
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

// Ревью 2026-08-30: оба поиска — через useRemoteSearch (защита от
// out-of-order ответов при быстрой печати).
const staff = useRemoteSearch((q) => fetchUsers({ q, page_size: 20 }), {
  onError: (e) => message.error(parseApiError(e, t)),
})
const staffOptions = staff.options
const staffSearching = staff.searching
const searchStaff = staff.search

// Внешние учётки: импорт допускает 1000 строк — серверный поиск с лимитом,
// заблокированные учётки не предлагаются.
const accounts = useRemoteSearch((q) => fetchLearningAccounts({ q, limit: 50 }), {
  onlyActive: true,
  onError: (e) => message.error(parseApiError(e, t)),
})
const accountOptions = accounts.options
const accountsSearching = accounts.searching
const searchAccounts = accounts.search

function openEnroll() {
  enrollKind.value = 'staff'
  staffIds.value = []
  accountId.value = null
  void searchStaff('')
  void searchAccounts('')
  enrollOpen.value = true
}

async function submitEnroll() {
  // Сотрудники — групповое зачисление выборкой (этап 2, §15), хоть бы один;
  // внешние учётки — по-прежнему по одной.
  if (enrollKind.value === 'staff') {
    if (staffIds.value.length === 0) {
      message.error(t('learning.participants.pickRequired'))
      return
    }
    try {
      const result: {
        enrolled: number
        skipped_duplicates: number
        errors?: { user_id: string; message: string }[]
      } = await bulkEnrollMut.mutateAsync({
        courseId: props.courseId,
        userIds: staffIds.value,
      })
      message.success(
        t('learning.participants.bulkEnrolled', {
          enrolled: result.enrolled,
          skipped: result.skipped_duplicates,
        }),
      )
      // Ревью 2026-08-30: errors[] (например «сотрудник не найден» гонки
      // удаления) не должен теряться — зелёный успех без зачисленных людей.
      const failed = result.errors ?? []
      if (failed.length > 0) {
        message.warning(
          t('learning.participants.bulkErrors', {
            count: failed.length,
            first: failed[0]?.message ?? '',
          }),
        )
      }
      enrollOpen.value = false
    } catch {
      // ошибка уже показана в watch
    }
    return
  }
  if (!accountId.value) {
    message.error(t('learning.participants.pickRequired'))
    return
  }
  try {
    await enrollMut.mutateAsync({
      courseId: props.courseId,
      body: { user_id: null, learning_account_id: accountId.value },
    })
    message.success(t('learning.participants.enrolled'))
    enrollOpen.value = false
  } catch {
    // ошибка уже показана в watch
  }
}

async function removeParticipant(row: LearningParticipantRow) {
  try {
    await unenrollMut.mutateAsync({ courseId: props.courseId, participantId: row.id })
    message.success(t('learning.participants.removed'))
  } catch {
    // ошибка уже показана в watch
  }
}

// Сертификат сотрудника: скачать выданный либо выпустить за полностью
// пройденный курс (бэкенд идемпотентен — ensure_certificate).
const certBusy = ref<string | null>(null)

function hasCertAccess(row: LearningParticipantRow): boolean {
  return !!row.has_certificate
    || (row.progress_total > 0 && row.progress_completed === row.progress_total)
}

async function downloadCertificate(row: LearningParticipantRow) {
  certBusy.value = row.id
  try {
    const blob = await fetchParticipantCertificateBlob(props.courseId, row.id)
    downloadBlob(blob, `certificate-${row.id}.pdf`)
    message.success(t('learning.participants.certReady'))
    // has_certificate в строке мог появиться (сертификат выпущен сейчас)
    void query.refetch()
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    certBusy.value = null
  }
}

const columns = computed<DataTableColumns<LearningParticipantRow>>(() => [
  {
    type: 'expand',
    renderExpand: (row) =>
      h(ParticipantItemsDetail, { courseId: props.courseId, participantId: row.id }),
  },
  {
    title: t('learning.participants.colName'),
    key: 'display_name',
    minWidth: 120,
    render: (r) => r.display_name,
  },
  { title: t('learning.participants.colEmail'), key: 'email', width: 140, ellipsis: { tooltip: true } },
  {
    title: t('learning.participants.colKind'),
    key: 'participant_kind',
    // 150: тег «Сотрудник портала» (~130px) не наезжает на соседнюю колонку
    width: 150,
    render: (r) =>
      h(
        NTag,
        { size: 'tiny', bordered: false, type: r.participant_kind === 'staff' ? 'info' : 'default' },
        { default: () => (r.participant_kind === 'staff' ? t('learning.participants.kindStaff') : t('learning.participants.kindExternal')) },
      ),
  },
  {
    title: t('learning.participants.colProgress'),
    key: 'progress',
    width: 110,
    render: (r) => `${r.progress_completed} / ${r.progress_total}`,
  },
  {
    title: t('learning.participants.colActions'),
    key: 'actions',
    // 240: «Сертификат» + «Исключить» одной строкой (ревью UI 2026-09-01:
    // сертификат — это действие, живёт рядом с остальными действиями)
    width: 240,
    render: (r) =>
      h('div', { class: 'row-actions' }, [
        hasCertAccess(r)
          ? h(
              NButton,
              {
                size: 'tiny',
                type: 'success',
                secondary: true,
                loading: certBusy.value === r.id,
                onClick: () => void downloadCertificate(r),
              },
              { default: () => t('learning.participants.certificate') },
            )
          : null,
        // Ревью 2026-08-30: деструктивное действие — с подтверждением (как
        // удаление курса в CoursesTab).
        h(
          NPopconfirm,
          { onPositiveClick: () => removeParticipant(r) },
          {
            trigger: () =>
              h(
                NButton,
                { size: 'tiny', type: 'error', quaternary: true },
                { default: () => t('learning.participants.remove') },
              ),
            default: () => t('learning.participants.removeConfirm'),
          },
        ),
      ]),
  },
])
</script>

<style scoped>
/* действия создаются через h() в render-колбэке колонок — scoped-стиль
   дотягивается только через :deep() */
:deep(.row-actions) {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}

.panel-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.panel-draft-hint {
  margin: -6px 0 12px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
