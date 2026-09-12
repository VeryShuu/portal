<template>
  <section class="profile-card profile-card--wide">
    <header class="profile-card__head">
      <h2 class="profile-card__title">
        {{ t('users.password.changeTitle') }}
      </h2>
    </header>
    <n-alert
      v-if="error"
      type="error"
      closable
      style="margin-bottom: 12px"
      @close="error = null"
    >
      {{ error }}
    </n-alert>
    <n-alert
      v-if="success"
      type="success"
      closable
      style="margin-bottom: 12px"
      @close="success = false"
    >
      {{ t('users.password.changed') }}
    </n-alert>
    <n-form
      :model="form"
      label-placement="top"
      class="password-form"
    >
      <n-form-item :label="t('users.password.current')">
        <n-input
          v-model:value="form.current"
          type="password"
          show-password-on="click"
          :input-props="{ autocomplete: 'current-password' }"
        />
      </n-form-item>
      <n-form-item :label="t('users.password.new')">
        <n-input
          v-model:value="form.next"
          type="password"
          show-password-on="click"
          :input-props="{ autocomplete: 'new-password' }"
        />
      </n-form-item>
      <n-form-item :label="t('users.password.confirm')">
        <n-input
          v-model:value="form.confirm"
          type="password"
          show-password-on="click"
          :input-props="{ autocomplete: 'new-password' }"
        />
      </n-form-item>
    </n-form>
    <div class="card-actions">
      <n-button
        type="primary"
        :loading="saving"
        :disabled="!canSave"
        @click="save"
      >
        {{ t('users.password.save') }}
      </n-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAlert, NForm, NFormItem, NInput, NButton } from 'naive-ui'
import { changePassword } from '../../api/auth'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()

const form = ref({ current: '', next: '', confirm: '' })
const saving = ref(false)
const error = ref<string | null>(null)
const success = ref(false)

const canSave = computed(() =>
  form.value.current.length > 0 &&
  form.value.next.length >= 8 &&
  form.value.next === form.value.confirm,
)

async function save() {
  error.value = null
  success.value = false
  if (form.value.next !== form.value.confirm) {
    error.value = t('users.password.mismatch')
    return
  }
  saving.value = true
  try {
    await changePassword(form.value.current, form.value.next)
    success.value = true
    form.value = { current: '', next: '', confirm: '' }
  } catch (err: unknown) {
    const e = err as { status?: number }
    if (e?.status === 401) {
      error.value = t('users.password.wrongCurrent')
    } else {
      error.value = parseApiError(err, t)
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.profile-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  box-shadow: var(--shadow-sm);
}
.profile-card--wide {
  grid-column: 1 / -1;
}
.profile-card__head {
  margin-bottom: 16px;
}
.profile-card__title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}
.card-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.password-form {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
@media (max-width: 960px) {
  .password-form { grid-template-columns: 1fr; gap: 0; }
}
</style>
