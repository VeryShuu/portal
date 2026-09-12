<template>
  <n-spin :show="isLoading">
    <n-form
      v-if="form"
      label-placement="top"
      :show-feedback="false"
    >
      <div class="kb-grid">
        <n-form-item :label="t('admin.matrix.accessToken')">
          <n-input
            v-model:value="form.access_token"
            type="password"
            show-password-on="click"
            :placeholder="
              tokenSet
                ? t('admin.matrix.tokenKeep')
                : t('admin.matrix.tokenPlaceholder')
            "
            :input-props="{ autocomplete: 'new-password' }"
          />
        </n-form-item>
        <n-form-item :label="t('admin.matrix.homeserverUrl')">
          <n-input
            v-model:value="form.homeserver_url"
            :placeholder="t('admin.matrix.homeserverPlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('admin.matrix.serverName')">
          <n-input
            v-model:value="form.server_name"
            :placeholder="t('admin.matrix.serverNamePlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('admin.matrix.botUserId')">
          <n-input
            v-model:value="form.bot_user_id"
            :placeholder="t('admin.matrix.botUserIdPlaceholder')"
          />
        </n-form-item>
      </div>

      <div class="matrix-bot__toggle">
        <n-checkbox v-model:checked="form.enabled">
          {{ t('admin.matrix.enabled') }}
        </n-checkbox>
      </div>

      <div class="matrix-bot__hint">
        {{ t('admin.matrix.hint') }}
      </div>

      <div
        v-if="!fieldsReady"
        class="matrix-bot__notconfigured"
      >
        {{ t('admin.matrix.notConfigured') }}
      </div>
      <div
        v-else-if="!form.enabled"
        class="matrix-bot__status matrix-bot__status--off"
      >
        {{ t('admin.matrix.configuredDisabled') }}
      </div>
      <div
        v-else
        class="matrix-bot__status matrix-bot__status--on"
      >
        {{ t('admin.matrix.configuredEnabled') }}
      </div>

      <div class="matrix-bot__test-target">
        <n-form-item :label="t('admin.matrix.testTarget')">
          <n-input
            v-model:value="testTarget"
            :placeholder="t('admin.matrix.testTargetPlaceholder')"
            :maxlength="255"
            clearable
          />
        </n-form-item>
        <div class="matrix-bot__hint">
          {{ t('admin.matrix.testTargetHint') }}
        </div>
      </div>

      <div class="email-actions">
        <n-button
          type="primary"
          :loading="putMut.isPending.value"
          :disabled="!isDirty"
          @click="onSave"
        >
          {{ t('common.save') }}
        </n-button>
        <n-button
          :loading="testing"
          :disabled="!tokenSet"
          @click="onTest"
        >
          {{ t('admin.matrix.test') }}
        </n-button>
      </div>

      <div
        v-if="testResult"
        class="kc-test-result"
        :class="testResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
      >
        <div class="kc-test-result__title">
          {{
            testResult.ok
              ? t('admin.matrix.testOk')
              : t('admin.matrix.testFail')
          }}
        </div>
        <div
          v-if="testResult.detail || testResult.error"
          class="kc-test-result__details"
        >
          {{ testResult.detail || testResult.error }}
        </div>
      </div>
    </n-form>
  </n-spin>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, NSpin, NForm, NFormItem, NInput, NCheckbox, NButton } from 'naive-ui'
import type { MatrixBotSettingsIn, MatrixBotTestResult } from '../../api/matrixBot'
import { testMatrixBot } from '../../api/matrixBot'
import { useMatrixBotQuery, usePutMatrixBotMutation } from '../../queries/admin'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const message = useMessage()

const { data, isLoading } = useMatrixBotQuery()
const putMut = usePutMatrixBotMutation()

interface MatrixBotFormState {
  access_token: string | null
  homeserver_url: string | null
  server_name: string | null
  bot_user_id: string | null
  enabled: boolean
}

const form = ref<MatrixBotFormState | null>(null)
const tokenSet = ref(false)
const isDirty = ref(false)

// Заполняем форму из ответа один раз; затем следим за изменениями для dirty.
watch(
  data,
  (d) => {
    if (!d) return
    tokenSet.value = d.access_token_set
    form.value = {
      // write-only: никогда не предзаполняем токен.
      access_token: null,
      homeserver_url: d.homeserver_url ?? null,
      server_name: d.server_name ?? null,
      bot_user_id: d.bot_user_id ?? null,
      enabled: d.enabled,
    }
    isDirty.value = false
  },
  { immediate: true },
)

// Все ли реквизиты заполнены (без учёса переключателя): честные состояния
// баннера — «не хватает полей» / «настроено, но выключено» / «включено».
const fieldsReady = computed(
  () => tokenSet.value && !!form.value?.homeserver_url && !!form.value?.bot_user_id,
)

watch(
  form,
  () => {
    if (form.value) isDirty.value = true
  },
  { deep: true },
)

function buildDto(): MatrixBotSettingsIn {
  const f = form.value
  if (!f) throw new Error('form is not loaded')
  const dto: MatrixBotSettingsIn = {
    enabled: f.enabled,
    homeserver_url: f.homeserver_url,
    server_name: f.server_name,
    bot_user_id: f.bot_user_id,
  }
  // Токен: передаём только если пользователь что-то ввёл. На enabled=true
  // при отсутствии ранее сохранённого токена бэкенд вернёт 400.
  if (f.access_token) {
    dto.access_token = f.access_token
  }
  return dto
}

async function onSave() {
  if (!form.value) return
  if (form.value.enabled && !tokenSet.value && !form.value.access_token) {
    message.error(t('admin.matrix.tokenRequired'))
    return
  }
  if (form.value.enabled && !(form.value.homeserver_url && form.value.bot_user_id)) {
    message.error(t('admin.matrix.requiredFields'))
    return
  }
  try {
    await putMut.mutateAsync(buildDto())
    message.success(t('admin.modules.saved'))
    // После save бэкенд возвращает обновлённый out; query инвалидируется,
    // watch(data) снова выставит access_token=null.
    form.value.access_token = null
    isDirty.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

const testing = ref(false)
const testResult = ref<MatrixBotTestResult | null>(null)
// Кому слать тест: MXID / email / localpart; пусто → сам админ (по конвенции).
const testTarget = ref<string | null>(null)
async function onTest() {
  testing.value = true
  testResult.value = null
  try {
    const target = testTarget.value?.trim() || null
    testResult.value = await testMatrixBot(target)
  } catch (e) {
    testResult.value = { ok: false, error: parseApiError(e, t) }
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.kb-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.matrix-bot__toggle {
  margin: 16px 0 8px;
}
.matrix-bot__hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.matrix-bot__notconfigured {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.matrix-bot__status {
  font-size: 13px;
  margin-bottom: 12px;
}
.matrix-bot__status--off {
  color: var(--color-text-secondary);
}
.matrix-bot__status--on {
  color: var(--color-success, #18a058);
}
.matrix-bot__test-target {
  margin-top: 16px;
}
.email-actions {
  display: flex;
  gap: 12px;
}
</style>
