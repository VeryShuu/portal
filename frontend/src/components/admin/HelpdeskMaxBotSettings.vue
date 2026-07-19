<template>
  <n-spin :show="isLoading">
    <n-form
      v-if="form"
      label-placement="top"
      :show-feedback="false"
    >
      <div class="kb-grid">
        <n-form-item :label="t('admin.helpdesk.max.botToken')">
          <n-input
            v-model:value="form.bot_token"
            type="password"
            show-password-on="click"
            :placeholder="
              tokenSet
                ? t('admin.helpdesk.max.tokenKeep')
                : t('admin.helpdesk.max.tokenPlaceholder')
            "
            :input-props="{ autocomplete: 'new-password' }"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.max.chatId')">
          <n-input
            v-model:value="form.chat_id"
            :placeholder="t('admin.helpdesk.max.chatIdPlaceholder')"
          />
        </n-form-item>
      </div>

      <div class="helpdesk-max__toggle">
        <n-checkbox v-model:checked="form.enabled">
          {{ t('admin.helpdesk.max.enabled') }}
        </n-checkbox>
      </div>

      <div class="helpdesk-max__hint">
        {{ t('admin.helpdesk.max.chatIdHint') }}
      </div>

      <div
        v-if="!configured"
        class="helpdesk-max__notconfigured"
      >
        {{ t('admin.helpdesk.max.notConfigured') }}
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
          {{ t('admin.helpdesk.max.test') }}
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
              ? t('admin.helpdesk.max.testOk')
              : t('admin.helpdesk.max.testFail')
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
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, NSpin, NForm, NFormItem, NInput, NCheckbox, NButton } from 'naive-ui'
import type { HelpdeskMaxBotSettingsIn, HelpdeskMaxBotTestResult } from '../../api/helpdesk'
import { testHelpdeskMaxBot } from '../../api/helpdesk'
import { useHelpdeskMaxBotQuery, usePutHelpdeskMaxBotMutation } from '../../queries/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const message = useMessage()

const { data, isLoading } = useHelpdeskMaxBotQuery()
const putMut = usePutHelpdeskMaxBotMutation()

interface MaxBotFormState {
  bot_token: string | null
  chat_id: string | null
  enabled: boolean
}

const EMPTY: MaxBotFormState = {
  bot_token: null,
  chat_id: null,
  enabled: false,
}

const form = ref<MaxBotFormState | null>(null)
const configured = ref(false)
const tokenSet = ref(false)
const isDirty = ref(false)

// Заполняем форму из ответа один раз; затем следим за изменениями для dirty.
watch(
  data,
  (d) => {
    if (!d) return
    configured.value = d.configured
    tokenSet.value = d.bot_token_set
    form.value = {
      // write-only: никогда не предзаполняем токен.
      bot_token: null,
      chat_id: d.chat_id ?? null,
      enabled: d.enabled,
    }
    isDirty.value = false
  },
  { immediate: true },
)

watch(
  form,
  () => {
    if (form.value) isDirty.value = true
  },
  { deep: true },
)

function buildDto(): HelpdeskMaxBotSettingsIn {
  const f = form.value ?? EMPTY
  const dto: HelpdeskMaxBotSettingsIn = {
    enabled: f.enabled,
    chat_id: f.chat_id,
  }
  // Токен: передаём только если пользователь что-то ввёл. На enabled=true
  // при отсутствии ранее сохранённого токена бэкенд вернёт 400.
  if (f.bot_token) {
    dto.bot_token = f.bot_token
  }
  return dto
}

async function onSave() {
  if (!form.value) return
  if (form.value.enabled && !tokenSet.value && !form.value.bot_token) {
    message.error(t('admin.helpdesk.max.tokenRequired'))
    return
  }
  try {
    await putMut.mutateAsync(buildDto())
    message.success(t('admin.modules.saved'))
    // После save бэкенд возвращает обновлённый out; query инвалидируется,
    // watch(data) снова выставит bot_token=null.
    form.value.bot_token = null
    isDirty.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

const testing = ref(false)
const testResult = ref<HelpdeskMaxBotTestResult | null>(null)
async function onTest() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testHelpdeskMaxBot()
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
.helpdesk-max__toggle {
  margin: 16px 0 8px;
}
.helpdesk-max__hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.helpdesk-max__notconfigured {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.email-actions {
  display: flex;
  gap: 12px;
}
</style>
