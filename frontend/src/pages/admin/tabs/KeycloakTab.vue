<template>
  <div class="branding-wrap">
    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.keycloak.oidcTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.keycloak.oidcHint') }}
      </div>
      <n-form
        :model="kcForm"
        label-placement="top"
      >
        <div class="branding-fields">
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.keycloak.url')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="kcForm.keycloak_url"
                :placeholder="t('admin.keycloak.urlPlaceholder')"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.keycloak.realm')"
              style="margin-bottom:0;width:200px"
            >
              <n-input
                v-model:value="kcForm.keycloak_realm"
                :placeholder="t('admin.keycloak.realmPlaceholder')"
              />
            </n-form-item>
          </div>
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.keycloak.oidcClientId')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="kcForm.oidc_client_id"
                :placeholder="t('admin.keycloak.oidcClientIdPlaceholder')"
                :input-props="{ autocomplete: 'username' }"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.keycloak.oidcClientSecret')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="kcForm.oidc_client_secret"
                type="password"
                show-password-on="click"
                :placeholder="kcSettings?.oidc_client_secret_set ? t('admin.keycloak.oidcClientSecretKeep') : t('admin.keycloak.oidcClientSecretPlaceholder')"
                :input-props="{ autocomplete: 'new-password' }"
              />
            </n-form-item>
          </div>
        </div>
      </n-form>
      <div class="email-actions">
        <n-button
          type="primary"
          :loading="kcSaving"
          @click="saveKcSettings"
        >
          {{ t('admin.keycloak.save') }}
        </n-button>
        <n-button
          :loading="kcTestingOidc"
          @click="testOidcConnection"
        >
          {{ t('admin.keycloak.testOidc') }}
        </n-button>
      </div>
      <div
        v-if="kcOidcTestResult"
        class="kc-test-result"
        :class="kcOidcTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
      >
        <div class="kc-test-result__title">
          {{ kcOidcTestResult.ok ? t('admin.keycloak.testOidcOk') : t('admin.keycloak.testOidcFail') }}
        </div>
        <div
          v-if="kcOidcTestResult.details"
          class="kc-test-result__details"
        >
          {{ kcOidcTestResult.details }}
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.keycloak.syncTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.keycloak.syncHint') }}
      </div>
      <n-form
        :model="kcForm"
        label-placement="top"
      >
        <div class="branding-fields">
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.keycloak.syncClientId')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="kcForm.sync_client_id"
                :placeholder="t('admin.keycloak.syncClientIdPlaceholder')"
                clearable
                :input-props="{ autocomplete: 'username' }"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.keycloak.syncClientSecret')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="kcForm.sync_client_secret"
                type="password"
                show-password-on="click"
                :placeholder="kcSettings?.sync_client_secret_set ? t('admin.keycloak.syncClientSecretKeep') : t('admin.keycloak.syncClientSecretPlaceholder')"
                clearable
                :input-props="{ autocomplete: 'new-password' }"
              />
            </n-form-item>
          </div>
          <div style="font-size:12px;color:var(--color-text-secondary)">
            {{ t('admin.keycloak.syncClientSecretClearHint') }}
          </div>
        </div>
      </n-form>
      <div class="email-actions">
        <n-button
          type="primary"
          :loading="kcSaving"
          @click="saveKcSettings"
        >
          {{ t('admin.keycloak.saveSyncSettings') }}
        </n-button>
        <n-button
          :loading="kcTestingSync"
          @click="testSyncConnection"
        >
          {{ t('admin.keycloak.testSync') }}
        </n-button>
      </div>
      <div
        v-if="kcSyncTestResult"
        class="kc-test-result"
        :class="kcSyncTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
      >
        <div class="kc-test-result__title">
          {{ kcSyncTestResult.ok ? t('admin.keycloak.testSyncOk') : t('admin.keycloak.testSyncFail') }}
        </div>
        <div
          v-if="kcSyncTestResult.details"
          class="kc-test-result__details"
        >
          {{ kcSyncTestResult.details }}
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.keycloak.syncStatusTitle') }}
      </div>
      <div class="kc-sync-status">
        <div class="kc-sync-row">
          <span class="kc-sync-label">{{ t('admin.keycloak.lastSyncAt') }}</span>
          <span class="kc-sync-value">{{ kcSyncStatus?.last_run_at ? new Date(kcSyncStatus.last_run_at).toLocaleString() : t('admin.keycloak.syncNever') }}</span>
        </div>
        <div
          v-if="kcSyncStatus?.last_count != null"
          class="kc-sync-row"
        >
          <span class="kc-sync-label">{{ t('admin.keycloak.lastSyncCount') }}</span>
          <span class="kc-sync-value">{{ kcSyncStatus.last_count }}</span>
        </div>
        <div
          v-if="kcSyncStatus?.last_status"
          class="kc-sync-row"
        >
          <span class="kc-sync-label">{{ t('admin.keycloak.lastSyncStatus') }}</span>
          <n-tag
            :type="kcSyncStatus.last_status === 'ok' ? 'success' : 'error'"
            size="small"
            :bordered="false"
          >
            {{ kcSyncStatus.last_status === 'ok' ? t('admin.keycloak.syncStatusOk') : t('admin.keycloak.syncStatusError') }}
          </n-tag>
        </div>
        <div class="kc-sync-row">
          <span
            class="kc-sync-label"
            style="color:var(--color-text-secondary);font-size:12px"
          >{{ t('admin.keycloak.syncScheduleHint') }}</span>
        </div>
      </div>
      <div
        class="email-actions"
        style="margin-top:16px"
      >
        <n-button
          :loading="syncing"
          @click="syncUsers"
        >
          <template #icon>
            <n-icon><SyncOutline /></n-icon>
          </template>
          {{ syncing ? t('admin.users.syncing') : t('admin.keycloak.syncNow') }}
        </n-button>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.keycloak.guideTitle') }}
      </div>
      <n-collapse>
        <n-collapse-item
          :title="t('admin.keycloak.guideOidcTitle')"
          name="oidc"
        >
          <ol class="kc-guide-list">
            <li>{{ t('admin.keycloak.guideOidcStep1') }}</li>
            <li>{{ t('admin.keycloak.guideOidcStep2') }}</li>
            <li>{{ t('admin.keycloak.guideOidcStep3') }}</li>
            <li>{{ t('admin.keycloak.guideOidcStep4') }}</li>
            <li>{{ t('admin.keycloak.guideOidcStep5') }}</li>
            <li>{{ t('admin.keycloak.guideOidcStep6') }}</li>
            <li>{{ t('admin.keycloak.guideOidcStep7') }}</li>
          </ol>
        </n-collapse-item>
        <n-collapse-item
          :title="t('admin.keycloak.guideSyncTitle')"
          name="sync"
        >
          <ol class="kc-guide-list">
            <li>{{ t('admin.keycloak.guideSyncStep1') }}</li>
            <li>{{ t('admin.keycloak.guideSyncStep2') }}</li>
            <li>{{ t('admin.keycloak.guideSyncStep3') }}</li>
            <li>{{ t('admin.keycloak.guideSyncStep4') }}</li>
          </ol>
          <div class="kc-guide-note">
            <strong>{{ t('admin.keycloak.guideNoteTitle') }}</strong>
            <p>{{ t('admin.keycloak.guideNoteText') }}</p>
          </div>
        </n-collapse-item>
      </n-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NIcon, NTag, NCollapse, NCollapseItem, NForm, NFormItem, useMessage } from 'naive-ui'
import { SyncOutline } from '@vicons/ionicons5'
import { syncUsersFromKeycloak } from '../../../api/users'
import { api } from '../../../api'
import { useKeycloakSettingsQuery, useKeycloakSyncStatusQuery } from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()

interface KcTestResult {
  ok: boolean
  details?: string
}

const kcSaving = ref(false)
const kcTestingOidc = ref(false)
const kcTestingSync = ref(false)
const kcOidcTestResult = ref<KcTestResult | null>(null)
const kcSyncTestResult = ref<KcTestResult | null>(null)
const syncing = ref(false)
const kcLoadError = ref(false)

const kcForm = ref({
  keycloak_url: '',
  keycloak_realm: '',
  oidc_client_id: '',
  oidc_client_secret: '',
  sync_client_id: '',
  sync_client_secret: '',
})

const { data: kcSettingsData, isError: kcSettingsFailed } = useKeycloakSettingsQuery()
const { data: kcSyncStatusData } = useKeycloakSyncStatusQuery()

const kcSettings = computed(() => kcSettingsData.value ?? null)
const kcSyncStatus = computed(() => kcSyncStatusData.value ?? null)

watch(kcSettingsData, (data) => {
  if (data) {
    kcForm.value.keycloak_url = data.keycloak_url
    kcForm.value.keycloak_realm = data.keycloak_realm
    kcForm.value.oidc_client_id = data.oidc_client_id
    kcForm.value.oidc_client_secret = ''
    kcForm.value.sync_client_id = data.sync_client_id
    kcForm.value.sync_client_secret = ''
    kcLoadError.value = false
  }
}, { immediate: true })

watch(kcSettingsFailed, (failed) => {
  if (failed) {
    kcLoadError.value = true
    message.error(t('errors.generic'))
  }
})

async function saveKcSettings() {
  if (kcLoadError.value) {
    message.error(t('admin.keycloak.loadFailedGuard'))
    return
  }
  kcSaving.value = true
  try {
    const syncIdEmpty = kcForm.value.sync_client_id.trim() === ''
    const body: Record<string, string | null> = {
      keycloak_url: kcForm.value.keycloak_url,
      keycloak_realm: kcForm.value.keycloak_realm,
      oidc_client_id: kcForm.value.oidc_client_id,
      oidc_client_secret: kcForm.value.oidc_client_secret || null,
      sync_client_id: kcForm.value.sync_client_id,
      sync_client_secret: syncIdEmpty ? '' : (kcForm.value.sync_client_secret || null),
    }
    await api('/admin/keycloak/settings', { method: 'PUT', body })
    kcForm.value.oidc_client_secret = ''
    kcForm.value.sync_client_secret = ''
    qc.invalidateQueries({ queryKey: queryKeys.admin.keycloakSettings() })
    message.success(t('admin.keycloak.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    kcSaving.value = false
  }
}

async function testOidcConnection() {
  kcTestingOidc.value = true
  kcOidcTestResult.value = null
  try {
    const res = await api<Record<string, unknown>>('/admin/keycloak/test/oidc', { method: 'POST' })
    const ok = res.discovery_ok === true && res.token_ok !== false
    const parts: string[] = []
    if (res.issuer) parts.push(`Issuer: ${res.issuer}`)
    if (res.token_ok === true) parts.push('Token: OK')
    if (res.token_note) parts.push(String(res.token_note))
    if (res.discovery_error) parts.push(String(res.discovery_error))
    if (res.token_error) parts.push(String(res.token_error))
    kcOidcTestResult.value = { ok, details: parts.join(' · ') || undefined }
  } catch (e: unknown) {
    kcOidcTestResult.value = { ok: false, details: String(e) }
  } finally {
    kcTestingOidc.value = false
  }
}

async function testSyncConnection() {
  kcTestingSync.value = true
  kcSyncTestResult.value = null
  try {
    const body: Record<string, string | null> = {}
    if (kcForm.value.sync_client_id) body.sync_client_id = kcForm.value.sync_client_id
    if (kcForm.value.sync_client_secret) body.sync_client_secret = kcForm.value.sync_client_secret
    const res = await api<Record<string, unknown>>('/admin/keycloak/test/sync', { method: 'POST', body })
    const ok = res.token_ok === true && res.users_ok !== false
    const parts: string[] = []
    if (res.users_note) parts.push(String(res.users_note))
    if (res.token_error) parts.push(String(res.token_error))
    if (res.users_error) parts.push(String(res.users_error))
    kcSyncTestResult.value = { ok, details: parts.join(' · ') || undefined }
  } catch (e: unknown) {
    kcSyncTestResult.value = { ok: false, details: String(e) }
  } finally {
    kcTestingSync.value = false
  }
}

async function syncUsers() {
  syncing.value = true
  const prevTimestamp = kcSyncStatus.value?.last_run_at ?? null
  const prevStatus = kcSyncStatus.value?.last_status ?? null
  try {
    await syncUsersFromKeycloak()
    const deadline = Date.now() + 60_000
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 2000))
      await qc.invalidateQueries({ queryKey: queryKeys.admin.keycloakSyncStatus() })
      const current = qc.getQueryData<{ last_run_at: string | null; last_status: string | null }>(
        queryKeys.admin.keycloakSyncStatus(),
      )
      const changed =
        current?.last_run_at !== prevTimestamp ||
        current?.last_status !== prevStatus
      if (changed) break
    }
    message.success(t('admin.users.syncOk'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    syncing.value = false
  }
}
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
