<template>
  <section>
    <div class="toolbar">
      <n-input
        v-model:value="search"
        :placeholder="t('learning.accounts.searchPlaceholder')"
        clearable
        style="max-width: 320px"
      />
      <div class="toolbar-actions">
        <n-button @click="downloadTemplate">
          <template #icon>
            <n-icon><DownloadOutline /></n-icon>
          </template>
          {{ t('learning.accounts.downloadTemplate') }}
        </n-button>
        <n-button
          :loading="importMut.isPending.value"
          @click="fileInput?.click()"
        >
          <template #icon>
            <n-icon><CloudUploadOutline /></n-icon>
          </template>
          {{ t('learning.accounts.import') }}
        </n-button>
        <input
          ref="fileInput"
          class="file-input"
          type="file"
          :aria-label="t('learning.accounts.import')"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          @change="onImportFile"
        >
        <n-button
          type="primary"
          @click="showCreate = true"
        >
          <template #icon>
            <n-icon><AddOutline /></n-icon>
          </template>
          {{ t('learning.accounts.create') }}
        </n-button>
      </div>
    </div>

    <n-data-table
      :columns="columns"
      :data="rows"
      :loading="query.isLoading.value"
      :row-key="(a: LearningAccount) => a.id"
      :bordered="false"
      striped
    />

    <n-pagination
      v-if="total > pageSize"
      class="pager"
      :page="page"
      :page-size="pageSize"
      :item-count="total"
      @update:page="onPage"
    />

    <n-modal
      class="learning-account-modal"
      v-model:show="showCreate"
      preset="card"
      :title="t('learning.accounts.createTitle')"
      style="max-width: 520px"
    >
      <n-alert
        type="info"
        :show-icon="false"
        style="margin-bottom: 12px"
      >
        {{ t('learning.accounts.createHint') }}
      </n-alert>
      <n-form label-placement="top">
        <n-form-item
          :label="t('learning.accounts.emailField')"
          required
        >
          <n-input
            v-model:value="form.email"
            :maxlength="255"
            placeholder="user@company.ru"
          />
        </n-form-item>
        <n-form-item
          :label="t('learning.accounts.fullNameField')"
          required
        >
          <n-input
            v-model:value="form.full_name"
            :maxlength="255"
          />
        </n-form-item>
        <n-form-item :label="t('learning.accounts.departmentField')">
          <n-input
            v-model:value="form.department"
            :maxlength="255"
          />
        </n-form-item>
        <n-form-item :label="t('learning.accounts.positionField')">
          <n-input
            v-model:value="form.position"
            :maxlength="255"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-actions">
          <n-button @click="showCreate = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="createMut.isPending.value"
            @click="submitCreate"
          >
            {{ t('common.create') }}
          </n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      class="learning-account-modal"
      v-model:show="showImportReport"
      preset="card"
      :title="t('learning.accounts.importReportTitle')"
      style="max-width: 620px"
    >
      <n-alert
        v-if="importReport"
        :type="importReport.error_count ? 'warning' : 'success'"
        :title="t('learning.accounts.importSummary', {
          created: importReport.created,
          skipped: importReport.skipped_duplicates,
          errors: importReport.error_count,
        })"
      />
      <div
        v-if="importReport?.errors.length"
        class="import-errors"
      >
        <div
          v-for="error in importReport.errors"
          :key="`${error.row}-${error.message}`"
          class="import-error"
        >
          <strong>{{ t('learning.accounts.importRow', { row: error.row }) }}</strong>
          <span>{{ error.message }}</span>
        </div>
      </div>
      <template #footer>
        <div class="modal-actions">
          <n-button
            type="primary"
            @click="showImportReport = false"
          >
            {{ t('common.close') }}
          </n-button>
        </div>
      </template>
    </n-modal>
    <n-modal
      v-model:show="showIssuedCode"
      class="learning-account-modal"
      preset="card"
      :title="t('learning.accounts.issuedCodeTitle')"
      style="max-width: 480px"
    >
      <template v-if="issuedCode">
        <p class="issued-code__account">
          {{ t('learning.accounts.issuedCodeFor', { name: issuedCode.accountName }) }}
        </p>
        <div class="issued-code">
          <span class="issued-code__value">{{ issuedCode.code }}</span>
          <n-button
            size="small"
            @click="copyIssuedCode"
          >
            {{ t('learning.accounts.copyCode') }}
          </n-button>
        </div>
        <n-alert
          type="warning"
          :show-icon="false"
          style="margin-top: 12px"
        >
          {{ t('learning.accounts.issuedCodeNote', {
            minutes: issuedCode.minutes,
          }) }}
        </n-alert>
      </template>
      <template #footer>
        <div class="modal-actions">
          <n-button
            type="primary"
            @click="showIssuedCode = false"
          >
            {{ t('common.close') }}
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
  NAlert,
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NPagination,
  NPopconfirm,
  NTag,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { AddOutline, CloudUploadOutline, DownloadOutline } from '@vicons/ionicons5'
import {
  useAdminAccountsQuery,
  useBlockAccountMutation,
  useCreateAccountMutation,
  useImportAccountsMutation,
  useIssueAccountLoginCodeMutation,
} from '../../queries/learning'
import {
  downloadLearningAccountsTemplate,
  type LearningAccount,
  type LearningAccountImport,
} from '../../api/learning'
import { parseApiError } from '../../utils/parseApiError'
import { useDebounceFn } from '../../composables/useDebounceFn'
import { downloadBlob } from '../../utils/download'
import { useMutationErrorToasts } from '../../composables/useMutationErrorToasts'

const { t } = useI18n()
const message = useMessage()

const search = ref('')
// Ревью 2026-08-30: запрос на каждую клавишу — дебаунс; смена запроса
// сбрасывает страницу (иначе поиск со 2+ страницы уходит мимо выдачи).
const debouncedSearch = ref('')
const page = ref(1)
const pageSize = 20
const pushSearch = useDebounceFn((value: string) => {
  debouncedSearch.value = value
  page.value = 1
}, 300)

watch(search, (value) => pushSearch(value))

const params = computed(() => ({ q: debouncedSearch.value || undefined, limit: pageSize, offset: (page.value - 1) * pageSize }))
const query = useAdminAccountsQuery(params)
const rows = computed<LearningAccount[]>(() => query.data.value?.items ?? [])
const total = computed(() => query.data.value?.total ?? 0)

watch(() => query.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })

function onPage(p: number) {
  page.value = p
}

const showCreate = ref(false)
const form = ref({ email: '', full_name: '', department: '', position: '' })
const createMut = useCreateAccountMutation()
const importMut = useImportAccountsMutation()
const issueCodeMut = useIssueAccountLoginCodeMutation()
const blockMut = useBlockAccountMutation()

useMutationErrorToasts(
  [createMut.error, importMut.error, issueCodeMut.error, blockMut.error],
  (text) => message.error(text),
  t,
)

const fileInput = ref<HTMLInputElement | null>(null)
const importReport = ref<LearningAccountImport | null>(null)
const showImportReport = ref(false)

// Ручная выдача кода (запасной путь «письмо не дошло»): plaintext показывается
// один раз в модалке — его же нигде больше нет (backend хранит только хэш).
interface IssuedCode {
  code: string
  minutes: number
  accountName: string
}
const issuedCode = ref<IssuedCode | null>(null)
const showIssuedCode = ref(false)

async function onImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    importReport.value = await importMut.mutateAsync(file)
    showImportReport.value = true
  } catch {
    // ошибка уже показана в watch
  }
}

async function downloadTemplate() {
  try {
    const blob = await downloadLearningAccountsTemplate()
    downloadBlob(blob, 'learning-accounts-template.xlsx')
  } catch (error) {
    message.error(parseApiError(error, t))
  }
}

async function submitCreate() {
  if (!form.value.email.trim() || !form.value.full_name.trim()) {
    message.error(t('learning.accounts.requiredFields'))
    return
  }
  try {
    await createMut.mutateAsync({
      email: form.value.email.trim(),
      full_name: form.value.full_name.trim(),
      department: form.value.department.trim() || null,
      position: form.value.position.trim() || null,
    })
    message.success(t('learning.accounts.created'))
    showCreate.value = false
    form.value = { email: '', full_name: '', department: '', position: '' }
  } catch {
    // ошибка уже показана в watch
  }
}

async function issueLoginCode(account: LearningAccount) {
  try {
    const resp = await issueCodeMut.mutateAsync(account.id)
    issuedCode.value = {
      code: resp.code,
      minutes: minutesLeft(resp.expires_at),
      accountName: account.full_name,
    }
    showIssuedCode.value = true
  } catch {
    // ошибка уже показана в watch
  }
}

function minutesLeft(expiresAt: string): number {
  const minutes = Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 60000)
  return Math.max(minutes, 1)
}

async function copyIssuedCode() {
  if (!issuedCode.value) return
  try {
    await navigator.clipboard.writeText(issuedCode.value.code)
    message.success(t('learning.accounts.codeCopied'))
  } catch {
    message.error(t('learning.accounts.copyCodeFailed'))
  }
}

async function toggleBlock(account: LearningAccount) {
  try {
    await blockMut.mutateAsync({ accountId: account.id, blocked: account.status !== 'blocked' })
  } catch {
    // ошибка уже показана в watch
  }
}

const columns = computed<DataTableColumns<LearningAccount>>(() => [
  { title: t('learning.accounts.colName'), key: 'full_name' },
  { title: t('learning.accounts.colEmail'), key: 'email' },
  {
    title: t('learning.accounts.colStatus'),
    key: 'status',
    width: 140,
    render: (a) =>
      h(
        NTag,
        { size: 'small', type: a.status === 'active' ? 'success' : 'error', bordered: false },
        { default: () => (a.status === 'active' ? t('learning.accounts.active') : t('learning.accounts.blocked')) },
      ),
  },
  {
    title: t('learning.accounts.colLastLogin'),
    key: 'last_login_at',
    width: 180,
    render: (a) => (a.last_login_at ? new Date(a.last_login_at).toLocaleString() : '—'),
  },
  {
    title: t('learning.accounts.colActions'),
    key: 'actions',
    width: 240,
    render: (a) =>
      h('div', { class: 'row-actions' }, [
        // Выдача кода не деструктивна (старый код при этом гасится) — без
        // подтверждения; блокировка — с ним (ревью 2026-08-30).
        h(
          NButton,
          { size: 'small', onClick: () => issueLoginCode(a) },
          { default: () => t('learning.accounts.issueCode') },
        ),
        h(
          NPopconfirm,
          { onPositiveClick: () => toggleBlock(a) },
          {
            trigger: () =>
              h(
                NButton,
                {
                  size: 'small',
                  secondary: true,
                  type: a.status === 'active' ? 'error' : 'success',
                },
                {
                  default: () =>
                    a.status === 'active' ? t('learning.accounts.block') : t('learning.accounts.unblock'),
                },
              ),
            default: () =>
              a.status === 'active' ? t('learning.accounts.blockConfirm') : t('learning.accounts.unblockConfirm'),
          },
        ),
      ]),
  },
])
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.file-input {
  display: none;
}

.import-errors {
  max-height: 300px;
  margin-top: 16px;
  overflow: auto;
  border: 1px solid var(--border-color, #e5e5e5);
  border-radius: 6px;
}

.import-error {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 12px;
  padding: 8px 12px;
}

.import-error + .import-error {
  border-top: 1px solid var(--border-color, #e5e5e5);
}

.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.issued-code__account {
  margin: 0 0 12px;
  font-size: 14px;
}

.issued-code {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--border-color, #e5e5e5);
  border-radius: 6px;
}

.issued-code__value {
  font-family: monospace;
  font-size: 24px;
  letter-spacing: 6px;
  font-weight: 600;
}

:deep(.row-actions) {
  display: flex;
  gap: 8px;
}
</style>
