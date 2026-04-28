<template>
  <div class="admin-wrap">
      <header class="page-head">
        <h1 class="page-head__title">{{ t('admin.title') }}</h1>
      </header>

      <n-tabs v-model:value="activeTab" type="line" animated>
        <!-- ── USERS ── -->
        <n-tab-pane name="users" :tab="t('admin.tabs.users')">
          <div class="tab-toolbar">
            <n-input
              v-model:value="userSearch"
              :placeholder="t('common.search')"
              clearable
              style="max-width:260px"
            >
              <template #prefix><n-icon><SearchOutline /></n-icon></template>
            </n-input>
            <n-button :loading="syncing" @click="syncUsers">
              <template #icon><n-icon><SyncOutline /></n-icon></template>
              {{ syncing ? t('admin.users.syncing') : t('admin.users.syncFromKeycloak') }}
            </n-button>
          </div>

          <n-data-table
            :columns="userColumns"
            :data="filteredUsers"
            :loading="loadingUsers"
            :pagination="{ pageSize: 20 }"
            :row-key="(row: UserPublic) => row.id"
            striped
            class="data-table"
          />
        </n-tab-pane>

        <!-- ── SERVICE LINKS ── -->
        <n-tab-pane name="links" :tab="t('admin.tabs.links')">
          <div class="tab-toolbar">
            <n-input
              v-model:value="linkSearch"
              :placeholder="t('common.search')"
              clearable
              style="max-width:260px"
            >
              <template #prefix><n-icon><SearchOutline /></n-icon></template>
            </n-input>
            <n-button type="primary" @click="openAddLink">
              <template #icon><n-icon><AddOutline /></n-icon></template>
              {{ t('admin.links.add') }}
            </n-button>
          </div>

          <n-data-table
            :columns="linkColumns"
            :data="filteredLinks"
            :loading="loadingLinks"
            :pagination="{ pageSize: 20 }"
            :row-key="(row: ServiceLink) => row.id"
            striped
            class="data-table"
          />
        </n-tab-pane>

        <!-- ── EMAIL ── -->
        <n-tab-pane name="email" :tab="t('admin.email.tab')">
          <div class="branding-wrap">
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.email.serverTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.email.serverHint') }}</div>
              <div class="branding-fields">
                <div class="email-row-2">
                  <n-form-item :label="t('admin.email.host')" style="margin-bottom:0;flex:1">
                    <n-input v-model:value="emailForm.host" :placeholder="t('admin.email.hostPlaceholder')" />
                  </n-form-item>
                  <n-form-item :label="t('admin.email.port')" style="margin-bottom:0;width:110px">
                    <n-input-number v-model:value="emailForm.port" :min="1" :max="65535" style="width:100%" />
                  </n-form-item>
                </div>
                <n-form-item :label="t('admin.email.fromAddress')" style="margin-bottom:0">
                  <n-input v-model:value="emailForm.from_address" :placeholder="t('admin.email.fromAddressPlaceholder')" />
                </n-form-item>
                <div class="email-row-2">
                  <n-form-item :label="t('admin.email.username')" style="margin-bottom:0;flex:1">
                    <n-input v-model:value="emailForm.username" :placeholder="t('admin.email.usernamePlaceholder')" clearable />
                  </n-form-item>
                  <n-form-item :label="t('admin.email.password')" style="margin-bottom:0;flex:1">
                    <n-input
                      v-model:value="emailForm.password"
                      type="password"
                      show-password-on="click"
                      :placeholder="emailPasswordSet ? t('admin.email.passwordKeep') : t('admin.email.passwordPlaceholder')"
                      clearable
                    />
                  </n-form-item>
                </div>
                <n-form-item :label="t('admin.email.encryption')" style="margin-bottom:0">
                  <div class="email-switches">
                    <n-switch v-model:value="emailForm.use_tls" @update:value="v => { if (v) emailForm.use_starttls = false }">
                      <template #checked>TLS</template>
                      <template #unchecked>TLS</template>
                    </n-switch>
                    <span class="email-switch-label">TLS</span>
                    <n-switch v-model:value="emailForm.use_starttls" @update:value="v => { if (v) emailForm.use_tls = false }">
                      <template #checked>STARTTLS</template>
                      <template #unchecked>STARTTLS</template>
                    </n-switch>
                    <span class="email-switch-label">STARTTLS</span>
                  </div>
                </n-form-item>
              </div>
              <div class="email-actions">
                <n-button type="primary" :loading="emailSaving" @click="saveEmailSettings">
                  {{ t('common.save') }}
                </n-button>
                <n-button :loading="emailTesting" @click="openTestEmailModal">
                  {{ t('admin.email.sendTest') }}
                </n-button>
              </div>
            </div>
          </div>
        </n-tab-pane>

        <!-- ── SYSTEM ── -->
        <n-tab-pane name="system" :tab="t('admin.tabs.system')">
          <div class="branding-wrap">

            <!-- General -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.system.generalTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.system.generalHint') }}</div>
              <div class="branding-fields">
                <n-form-item :label="t('admin.system.portalBaseUrl')" style="margin-bottom:0">
                  <n-input v-model:value="sysForm.portal_base_url" :placeholder="t('admin.system.portalBaseUrlPlaceholder')" />
                </n-form-item>
                <n-form-item :label="t('admin.system.timezone')" style="margin-bottom:0;max-width:280px">
                  <n-input v-model:value="sysForm.timezone" :placeholder="t('admin.system.timezonePlaceholder')" />
                </n-form-item>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.timezoneHint') }}</div>
              </div>
            </div>

            <!-- Security -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.system.securityTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.system.securityHint') }}</div>
              <div class="branding-fields">
                <n-form-item :label="t('admin.system.allowedCidr')" style="margin-bottom:0">
                  <n-input v-model:value="sysForm.allowed_cidr" :placeholder="t('admin.system.allowedCidrPlaceholder')" />
                </n-form-item>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.allowedCidrHint') }}</div>
                <n-form-item :label="t('admin.system.maxUploadMb')" style="margin-bottom:0;max-width:200px">
                  <n-input-number v-model:value="sysForm.max_upload_size_mb" :min="1" :max="1024" />
                </n-form-item>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.maxUploadMbHint') }}</div>
              </div>
            </div>

            <!-- Observability -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.system.observabilityTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.system.observabilityHint') }}</div>
              <div class="branding-fields">
                <n-checkbox v-model:checked="sysForm.prometheus_metrics_enabled">
                  {{ t('admin.system.prometheusEnabled') }}
                </n-checkbox>
                <n-form-item :label="t('admin.system.logLevel')" style="margin-bottom:0;margin-top:12px;max-width:220px">
                  <n-select v-model:value="sysForm.log_level" :options="logLevelOptions" />
                </n-form-item>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.logLevelHint') }}</div>
                <div class="email-row-2" style="margin-top:12px">
                  <n-form-item :label="t('admin.system.logSlowRequestMs')" style="margin-bottom:0;flex:1;max-width:220px">
                    <n-input-number v-model:value="sysForm.log_slow_request_ms" :min="0" :max="60000" />
                  </n-form-item>
                  <n-form-item :label="t('admin.system.arqMaxJobs')" style="margin-bottom:0;flex:1;max-width:160px">
                    <n-input-number v-model:value="sysForm.arq_max_jobs" :min="1" :max="200" />
                  </n-form-item>
                </div>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.arqMaxJobsHint') }}</div>
                <n-form-item :label="t('admin.system.sentryDsn')" style="margin-bottom:0;margin-top:12px">
                  <n-input
                    v-model:value="sysForm.sentry_dsn"
                    type="password"
                    show-password-on="click"
                    :placeholder="sysSettings?.sentry_dsn_set ? t('admin.system.sentryDsnKeep') : t('admin.system.sentryDsnPlaceholder')"
                  />
                </n-form-item>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.sentryDsnHint') }}</div>
                <n-form-item :label="t('admin.system.logForceJson')" style="margin-bottom:0;margin-top:12px;max-width:260px">
                  <n-select v-model:value="sysForm.log_force_json" :options="logForceJsonOptions" />
                </n-form-item>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.logForceJsonHint') }}</div>
              </div>
            </div>

            <!-- File limits -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.system.fileLimitsTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.system.fileLimitsHint') }}</div>
              <div class="branding-fields">
                <div class="email-row-2">
                  <n-form-item :label="t('admin.system.newsAttachmentMb')" style="margin-bottom:0;flex:1">
                    <n-input-number v-model:value="sysForm.news_attachment_max_size_mb" :min="1" :max="1024" />
                  </n-form-item>
                  <n-form-item :label="t('admin.system.kbMediaMb')" style="margin-bottom:0;flex:1">
                    <n-input-number v-model:value="sysForm.kb_media_max_size_mb" :min="1" :max="512" />
                  </n-form-item>
                  <n-form-item :label="t('admin.system.kbAttachmentMb')" style="margin-bottom:0;flex:1">
                    <n-input-number v-model:value="sysForm.kb_attachment_max_size_mb" :min="1" :max="1024" />
                  </n-form-item>
                </div>
              </div>
            </div>

            <!-- Save + Nginx reload -->
            <div class="branding-section">
              <div class="email-actions">
                <n-button type="primary" :loading="sysSaving" @click="saveSystemSettings">
                  {{ t('admin.system.save') }}
                </n-button>
                <n-button :loading="sysNginxReloading" @click="reloadNginx">
                  <template #icon><n-icon><SyncOutline /></n-icon></template>
                  {{ t('admin.system.nginxReload') }}
                </n-button>
              </div>
              <div style="font-size:12px;color:var(--color-text-secondary);margin-top:8px">{{ t('admin.system.nginxReloadHint') }}</div>
            </div>

            <!-- TLS Certificate -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.system.tlsTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.system.tlsHint') }}</div>

              <div class="tls-status-row">
                <n-tag :type="tlsStatus?.cert_exists ? 'success' : 'warning'" size="small" :bordered="false">
                  {{ tlsStatus?.cert_exists ? t('admin.system.tlsCertExists') : t('admin.system.tlsCertMissing') }}
                </n-tag>
                <span v-if="tlsStatus?.cert_expires_at" class="tls-meta">
                  {{ t('admin.system.tlsCertExpires') }}: {{ tlsStatus.cert_expires_at }}
                </span>
                <span v-if="tlsStatus?.cert_subject" class="tls-meta">
                  {{ t('admin.system.tlsCertSubject') }}: {{ tlsStatus.cert_subject }}
                </span>
              </div>
              <div class="tls-status-row" style="margin-top:6px">
                <n-tag :type="tlsStatus?.key_exists ? 'success' : 'warning'" size="small" :bordered="false">
                  {{ tlsStatus?.key_exists ? t('admin.system.tlsKeyExists') : t('admin.system.tlsKeyMissing') }}
                </n-tag>
              </div>

              <div class="email-actions" style="margin-top:16px">
                <n-upload :show-file-list="false" accept=".pem,.crt,.cer" @change="(info) => uploadTlsFile('cert', info)">
                  <n-button>{{ t('admin.system.tlsUploadCert') }}</n-button>
                </n-upload>
                <n-upload :show-file-list="false" accept=".pem,.key" @change="(info) => uploadTlsFile('key', info)">
                  <n-button>{{ t('admin.system.tlsUploadKey') }}</n-button>
                </n-upload>
                <n-button v-if="tlsStatus?.cert_exists" quaternary type="error" @click="deleteTlsFile('cert')">
                  {{ t('admin.system.tlsDeleteCert') }}
                </n-button>
                <n-button v-if="tlsStatus?.key_exists" quaternary type="error" @click="deleteTlsFile('key')">
                  {{ t('admin.system.tlsDeleteKey') }}
                </n-button>
              </div>
            </div>

          </div>
        </n-tab-pane>

        <!-- ── KEYCLOAK ── -->
        <n-tab-pane name="keycloak" :tab="t('admin.keycloak.tab')">
          <div class="branding-wrap">

            <!-- OIDC client -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.keycloak.oidcTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.keycloak.oidcHint') }}</div>
              <div class="branding-fields">
                <div class="email-row-2">
                  <n-form-item :label="t('admin.keycloak.url')" style="margin-bottom:0;flex:1">
                    <n-input v-model:value="kcForm.keycloak_url" :placeholder="t('admin.keycloak.urlPlaceholder')" />
                  </n-form-item>
                  <n-form-item :label="t('admin.keycloak.realm')" style="margin-bottom:0;width:200px">
                    <n-input v-model:value="kcForm.keycloak_realm" :placeholder="t('admin.keycloak.realmPlaceholder')" />
                  </n-form-item>
                </div>
                <div class="email-row-2">
                  <n-form-item :label="t('admin.keycloak.oidcClientId')" style="margin-bottom:0;flex:1">
                    <n-input v-model:value="kcForm.oidc_client_id" :placeholder="t('admin.keycloak.oidcClientIdPlaceholder')" />
                  </n-form-item>
                  <n-form-item :label="t('admin.keycloak.oidcClientSecret')" style="margin-bottom:0;flex:1">
                    <n-input
                      v-model:value="kcForm.oidc_client_secret"
                      type="password"
                      show-password-on="click"
                      :placeholder="kcSettings?.oidc_client_secret_set ? t('admin.keycloak.oidcClientSecretKeep') : t('admin.keycloak.oidcClientSecretPlaceholder')"
                    />
                  </n-form-item>
                </div>
              </div>
              <div class="email-actions">
                <n-button type="primary" :loading="kcSaving" @click="saveKcSettings">
                  {{ t('admin.keycloak.save') }}
                </n-button>
                <n-button :loading="kcTestingOidc" @click="testOidcConnection">
                  {{ t('admin.keycloak.testOidc') }}
                </n-button>
              </div>
              <div v-if="kcOidcTestResult" class="kc-test-result" :class="kcOidcTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'">
                <div class="kc-test-result__title">{{ kcOidcTestResult.ok ? t('admin.keycloak.testOidcOk') : t('admin.keycloak.testOidcFail') }}</div>
                <div v-if="kcOidcTestResult.details" class="kc-test-result__details">{{ kcOidcTestResult.details }}</div>
              </div>
            </div>

            <!-- Sync client -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.keycloak.syncTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.keycloak.syncHint') }}</div>
              <div class="branding-fields">
                <div class="email-row-2">
                  <n-form-item :label="t('admin.keycloak.syncClientId')" style="margin-bottom:0;flex:1">
                    <n-input v-model:value="kcForm.sync_client_id" :placeholder="t('admin.keycloak.syncClientIdPlaceholder')" clearable />
                  </n-form-item>
                  <n-form-item :label="t('admin.keycloak.syncClientSecret')" style="margin-bottom:0;flex:1">
                    <n-input
                      v-model:value="kcForm.sync_client_secret"
                      type="password"
                      show-password-on="click"
                      :placeholder="kcSettings?.sync_client_secret_set ? t('admin.keycloak.syncClientSecretKeep') : t('admin.keycloak.syncClientSecretPlaceholder')"
                      clearable
                    />
                  </n-form-item>
                </div>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.keycloak.syncClientSecretClearHint') }}</div>
              </div>
              <div class="email-actions">
                <n-button :loading="kcTestingSync" @click="testSyncConnection">
                  {{ t('admin.keycloak.testSync') }}
                </n-button>
              </div>
              <div v-if="kcSyncTestResult" class="kc-test-result" :class="kcSyncTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'">
                <div class="kc-test-result__title">{{ kcSyncTestResult.ok ? t('admin.keycloak.testSyncOk') : t('admin.keycloak.testSyncFail') }}</div>
                <div v-if="kcSyncTestResult.details" class="kc-test-result__details">{{ kcSyncTestResult.details }}</div>
              </div>
            </div>

            <!-- Sync status -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.keycloak.syncStatusTitle') }}</div>
              <div class="kc-sync-status">
                <div class="kc-sync-row">
                  <span class="kc-sync-label">{{ t('admin.keycloak.lastSyncAt') }}</span>
                  <span class="kc-sync-value">{{ kcSyncStatus?.last_run_at ? new Date(kcSyncStatus.last_run_at).toLocaleString() : t('admin.keycloak.syncNever') }}</span>
                </div>
                <div v-if="kcSyncStatus?.last_count != null" class="kc-sync-row">
                  <span class="kc-sync-label">{{ t('admin.keycloak.lastSyncCount') }}</span>
                  <span class="kc-sync-value">{{ kcSyncStatus.last_count }}</span>
                </div>
                <div v-if="kcSyncStatus?.last_status" class="kc-sync-row">
                  <span class="kc-sync-label">{{ t('admin.keycloak.lastSyncStatus') }}</span>
                  <n-tag :type="kcSyncStatus.last_status === 'ok' ? 'success' : 'error'" size="small" :bordered="false">
                    {{ kcSyncStatus.last_status === 'ok' ? t('admin.keycloak.syncStatusOk') : t('admin.keycloak.syncStatusError') }}
                  </n-tag>
                </div>
                <div class="kc-sync-row">
                  <span class="kc-sync-label" style="color:var(--color-text-secondary);font-size:12px">{{ t('admin.keycloak.syncScheduleHint') }}</span>
                </div>
              </div>
              <div class="email-actions" style="margin-top:16px">
                <n-button :loading="syncing" @click="syncUsers">
                  <template #icon><n-icon><SyncOutline /></n-icon></template>
                  {{ syncing ? t('admin.users.syncing') : t('admin.keycloak.syncNow') }}
                </n-button>
              </div>
            </div>

            <!-- Keycloak setup guide -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.keycloak.guideTitle') }}</div>
              <n-collapse>
                <n-collapse-item :title="t('admin.keycloak.guideOidcTitle')" name="oidc">
                  <ol class="kc-guide-list">
                    <li>{{ t('admin.keycloak.guideOidcStep1') }}</li>
                    <li>{{ t('admin.keycloak.guideOidcStep2') }}</li>
                    <li>{{ t('admin.keycloak.guideOidcStep3') }}</li>
                    <li>{{ t('admin.keycloak.guideOidcStep4') }}</li>
                    <li>{{ t('admin.keycloak.guideOidcStep5') }}</li>
                    <li>{{ t('admin.keycloak.guideOidcStep6') }}</li>
                  </ol>
                </n-collapse-item>
                <n-collapse-item :title="t('admin.keycloak.guideSyncTitle')" name="sync">
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
        </n-tab-pane>

        <!-- ── BRANDING ── -->
        <n-tab-pane name="branding" :tab="t('admin.branding.tab')">
          <div class="branding-wrap">

            <!-- Logo -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.logoTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.branding.logoHint') }}</div>
              <div class="branding-logo-row">
                <div class="branding-logo-preview">
                  <img v-if="currentLogoUrl" :src="currentLogoUrl" class="branding-logo-img" alt="Logo" />
                  <div v-else class="branding-logo-placeholder">
                    <div class="logo-mark-preview"><span class="logo-mark-preview__dot" /></div>
                    <span class="branding-logo-placeholder__text">{{ t('admin.branding.logoDefault') }}</span>
                  </div>
                </div>
                <div class="branding-logo-actions">
                  <input ref="logoInputRef" type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" style="display:none" @change="onLogoFileChange" />
                  <n-button type="primary" :loading="logoUploading" @click="logoInputRef?.click()">{{ t('admin.branding.uploadLogo') }}</n-button>
                  <n-button v-if="currentLogoUrl" :loading="logoResetting" @click="onLogoReset">{{ t('admin.branding.resetLogo') }}</n-button>
                </div>
              </div>
            </div>

            <!-- Favicon -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.faviconTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.branding.faviconHint') }}</div>
              <div class="branding-logo-actions" style="flex-direction:row;align-items:center;gap:12px">
                <img v-if="currentFaviconUrl" :src="currentFaviconUrl" class="branding-favicon-preview" alt="Favicon" />
                <input ref="faviconInputRef" type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp,image/x-icon" style="display:none" @change="onFaviconFileChange" />
                <n-button type="primary" size="small" :loading="faviconUploading" @click="faviconInputRef?.click()">{{ t('admin.branding.uploadFavicon') }}</n-button>
                <n-button v-if="currentFaviconUrl" size="small" :loading="faviconResetting" @click="onFaviconReset">{{ t('admin.branding.resetFavicon') }}</n-button>
              </div>
            </div>

            <!-- Login background -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.loginBgTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.branding.loginBgHint') }}</div>
              <div class="branding-logo-row">
                <div v-if="currentLoginBgUrl" class="branding-loginbg-preview">
                  <img :src="currentLoginBgUrl" alt="Login BG" class="branding-loginbg-img" />
                </div>
                <div class="branding-logo-actions">
                  <input ref="loginBgInputRef" type="file" accept="image/png,image/jpeg,image/webp" style="display:none" @change="onLoginBgFileChange" />
                  <n-button type="primary" size="small" :loading="loginBgUploading" @click="loginBgInputRef?.click()">{{ t('admin.branding.uploadLoginBg') }}</n-button>
                  <n-button v-if="currentLoginBgUrl" size="small" :loading="loginBgResetting" @click="onLoginBgReset">{{ t('admin.branding.resetLoginBg') }}</n-button>
                </div>
              </div>
            </div>

            <!-- General settings -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.generalTitle') }}</div>
              <div class="branding-fields">
                <n-form-item :label="t('admin.branding.portalName')" style="margin-bottom:0">
                  <n-input v-model:value="brandingForm.portal_name" :placeholder="t('admin.branding.portalNamePlaceholder')" />
                </n-form-item>
                <n-form-item :label="t('admin.branding.portalTagline')" style="margin-bottom:0">
                  <n-input v-model:value="brandingForm.portal_tagline" :placeholder="t('admin.branding.portalTaglinePlaceholder')" />
                </n-form-item>
                <n-form-item :label="t('admin.branding.accentColor')" style="margin-bottom:0">
                  <div class="branding-color-row">
                    <input type="color" v-model="brandingForm.accent_color" class="branding-color-input" />
                    <n-input v-model:value="brandingForm.accent_color" style="width:120px;font-family:monospace" />
                    <div class="branding-color-swatch" :style="`background:${brandingForm.accent_color}`" />
                  </div>
                </n-form-item>
                <n-form-item :label="t('admin.branding.welcomeSubtitle')" style="margin-bottom:0">
                  <n-input v-model:value="brandingForm.welcome_subtitle" type="textarea" :rows="2" :placeholder="t('admin.branding.welcomeSubtitlePlaceholder')" />
                </n-form-item>
              </div>
              <n-button type="primary" :loading="brandingFormSaving" style="margin-top:16px" @click="saveBrandingForm">
                {{ t('common.save') }}
              </n-button>
            </div>

            <!-- Banner -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.bannerTitle') }}</div>
              <div class="branding-fields">
                <n-form-item :label="t('admin.branding.bannerEnabled')" style="margin-bottom:0">
                  <n-switch v-model:value="brandingForm.banner_enabled" />
                </n-form-item>
                <n-form-item :label="t('admin.branding.bannerText')" style="margin-bottom:0">
                  <n-input v-model:value="brandingForm.banner_text" type="textarea" :rows="2" :placeholder="t('admin.branding.bannerTextPlaceholder')" />
                </n-form-item>
                <n-form-item :label="t('admin.branding.bannerType')" style="margin-bottom:0">
                  <n-select
                    v-model:value="brandingForm.banner_type"
                    :options="bannerTypeOptions"
                    style="width:200px"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.branding.bannerExpires')" style="margin-bottom:0">
                  <n-input
                    v-model:value="brandingForm.banner_expires_at"
                    :placeholder="t('admin.branding.bannerExpiresPlaceholder')"
                    clearable
                    style="width:220px"
                  />
                  <span style="margin-left:8px;font-size:12px;color:var(--color-text-muted)">{{ t('admin.branding.bannerExpiresHint') }}</span>
                </n-form-item>
              </div>
              <n-button type="primary" :loading="brandingFormSaving" style="margin-top:16px" @click="saveBrandingForm">
                {{ t('common.save') }}
              </n-button>
            </div>

          </div>
        </n-tab-pane>

        <!-- ── MODULES ── -->
        <n-tab-pane name="modules" :tab="t('admin.tabs.modules')">
          <div class="branding-wrap">

            <!-- Photos (own module) -->
            <div class="branding-section">
              <div class="module-header">
                <div>
                  <div class="branding-section__title">{{ t('admin.modules.photos.title') }}</div>
                  <div class="branding-section__hint">{{ t('admin.modules.photos.hint') }}</div>
                </div>
                <n-switch v-model:value="modulesForm.photos.enabled" />
              </div>
              <template v-if="modulesForm.photos.enabled">
                <div class="branding-fields" style="margin-top:16px">
                  <div class="email-row-2">
                    <n-form-item :label="t('admin.modules.widgetLimit')" style="margin-bottom:0;max-width:200px">
                      <n-input-number v-model:value="modulesForm.photos.widget_limit" :min="1" :max="50" />
                    </n-form-item>
                    <n-form-item :label="t('admin.modules.photos.maxSizeMb')" style="margin-bottom:0;max-width:200px">
                      <n-input-number v-model:value="modulesForm.photos.max_size_mb" :min="1" :max="500" />
                    </n-form-item>
                  </div>
                  <n-form-item :label="t('admin.modules.photos.allowedMime')" style="margin-bottom:0">
                    <n-input
                      v-model:value="modulesForm.photos.allowed_mime"
                      :placeholder="t('admin.modules.photos.allowedMimePlaceholder')"
                    />
                  </n-form-item>
                  <n-form-item style="margin-bottom:0">
                    <n-checkbox v-model:checked="modulesForm.photos.strip_gps">
                      {{ t('admin.modules.photos.stripGps') }}
                    </n-checkbox>
                  </n-form-item>
                </div>
              </template>
              <div class="branding-fields" style="margin-top:16px">
                <n-form-item :label="t('admin.system.photoGalleryUrl')" style="margin-bottom:0">
                  <n-input v-model:value="sysForm.photo_gallery_url" :placeholder="t('admin.system.photoGalleryUrlPlaceholder')" clearable />
                </n-form-item>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.photoGalleryUrlHint') }}</div>
              </div>
              <div class="email-actions" style="margin-top:16px">
                <n-button type="primary" :loading="modulesPhotosSaving" @click="savePhotosModuleAndUrls">
                  {{ t('common.save') }}
                </n-button>
              </div>
            </div>

            <!-- Nextcloud -->
            <div class="branding-section">
              <div class="module-header">
                <div>
                  <div class="branding-section__title">{{ t('admin.modules.nextcloud.title') }}</div>
                  <div class="branding-section__hint">{{ t('admin.modules.nextcloud.hint') }}</div>
                </div>
                <n-switch v-model:value="modulesForm.nextcloud.enabled" />
              </div>
              <template v-if="modulesForm.nextcloud.enabled">
                <div class="branding-fields" style="margin-top:16px">
                  <n-form-item :label="t('admin.system.nextcloudUrl')" style="margin-bottom:0">
                    <n-input v-model:value="sysForm.nextcloud_url" :placeholder="t('admin.system.nextcloudUrlPlaceholder')" />
                  </n-form-item>
                  <div class="email-row-2">
                    <n-form-item :label="t('admin.system.ncUserIdField')" style="margin-bottom:0;flex:1">
                      <n-input v-model:value="sysForm.nc_user_id_field" :placeholder="t('admin.system.ncUserIdFieldPlaceholder')" />
                    </n-form-item>
                    <n-form-item :label="t('admin.system.ncServicePassword')" style="margin-bottom:0;flex:1">
                      <n-input
                        v-model:value="sysForm.nc_service_password"
                        type="password"
                        show-password-on="click"
                        :placeholder="sysSettings?.nc_service_app_password_set ? t('admin.system.ncServicePasswordKeep') : t('admin.system.ncServicePasswordPlaceholder')"
                      />
                    </n-form-item>
                  </div>
                  <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.ncUserIdFieldHint') }}</div>
                  <div class="email-actions" style="margin-top:8px">
                    <n-button :loading="ncTesting" @click="testNcConnection">
                      {{ t('admin.system.ncTestConnection') }}
                    </n-button>
                  </div>
                  <div v-if="ncTestResult" class="kc-test-result" :class="ncTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'" style="margin-top:8px">
                    <div class="kc-test-result__title">{{ ncTestResult.ok ? t('admin.system.ncTestOk') : t('admin.system.ncTestFail') }}</div>
                    <div v-if="ncTestResult.details" class="kc-test-result__details">{{ ncTestResult.details }}</div>
                  </div>
                </div>
              </template>
              <div class="email-actions" style="margin-top:16px">
                <n-button type="primary" :loading="modulesNextcloudSaving || ncConnectionSaving" @click="saveNextcloudAll">
                  {{ t('common.save') }}
                </n-button>
              </div>
            </div>

            <!-- Video Gallery -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.modules.videoGallery.title') }}</div>
              <div class="branding-section__hint">{{ t('admin.modules.videoGallery.hint') }}</div>
              <div class="branding-fields" style="margin-top:16px">
                <n-form-item :label="t('admin.system.videoGalleryUrl')" style="margin-bottom:0">
                  <n-input v-model:value="sysForm.video_gallery_url" :placeholder="t('admin.system.videoGalleryUrlPlaceholder')" clearable />
                </n-form-item>
                <div style="font-size:12px;color:var(--color-text-secondary)">{{ t('admin.system.videoGalleryUrlHint') }}</div>
              </div>
              <div class="email-actions" style="margin-top:16px">
                <n-button type="primary" :loading="sysSaving" @click="saveSystemSettings">
                  {{ t('common.save') }}
                </n-button>
              </div>
            </div>

          </div>
        </n-tab-pane>

      </n-tabs>

    <!-- ── LINK FORM MODAL ── -->
    <n-modal
      v-model:show="linkModalOpen"
      :title="editingLink ? t('admin.links.editTitle') : t('admin.links.addTitle')"
      preset="card"
      style="width:540px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form :model="linkForm" :rules="linkRules" ref="linkFormRef" label-placement="top">
        <div class="form-row">
          <n-form-item :label="t('admin.links.form.titleLabel')" path="title">
            <n-input v-model:value="linkForm.title" :placeholder="t('admin.links.form.titlePlaceholder')" />
          </n-form-item>
          <n-form-item :label="t('admin.links.form.urlLabel')" path="url">
            <n-input v-model:value="linkForm.url" :placeholder="t('admin.links.form.urlPlaceholder')" />
          </n-form-item>
        </div>
        <div class="form-row">
          <n-form-item :label="t('admin.links.form.categoryLabel')">
            <n-input v-model:value="linkForm.category" :placeholder="t('admin.links.form.categoryPlaceholder')" clearable />
          </n-form-item>
          <n-form-item :label="t('admin.links.form.sortOrderLabel')">
            <n-input-number v-model:value="linkForm.sort_order" :min="0" style="width:100%" />
          </n-form-item>
        </div>
        <n-form-item :label="t('admin.links.form.descriptionLabel')">
          <n-input
            v-model:value="linkForm.description"
            type="textarea"
            :rows="2"
            :placeholder="t('admin.links.form.descriptionPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item :label="t('admin.links.form.iconLabel')">
          <div class="icon-upload-row">
            <div v-if="iconPreview || (editingLink && editingLink.icon_url)" class="icon-preview-wrap">
              <img :src="iconPreview || editingLink!.icon_url!" class="icon-preview" alt="" />
              <n-button
                size="tiny" circle quaternary type="error"
                class="icon-preview-remove"
                @click="removeIcon"
              >×</n-button>
            </div>
            <n-upload
              accept="image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon"
              :max="1"
              :show-file-list="false"
              @change="onIconFileChange"
            >
              <n-button size="small">{{ t('admin.links.form.iconUploadBtn') }}</n-button>
            </n-upload>
          </div>
        </n-form-item>
        <div class="form-checks">
          <n-checkbox v-model:checked="linkForm.supports_sso">{{ t('admin.links.form.supportsSSO') }}</n-checkbox>
          <n-checkbox v-model:checked="linkForm.is_active">{{ t('admin.links.form.isActive') }}</n-checkbox>
        </div>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="linkModalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="savingLink" @click="submitLink">{{ t('common.save') }}</n-button>
        </div>
      </template>
    </n-modal>

    <!-- ── DELETE CONFIRM ── -->
    <n-modal
      v-model:show="deleteConfirmOpen"
      :title="t('admin.links.confirmDelete', { title: deletingLink?.title ?? '' })"
      preset="dialog"
      type="warning"
      :positive-text="t('common.delete')"
      :negative-text="t('common.cancel')"
      @positive-click="confirmDelete"
    >
      {{ t('admin.links.confirmDeleteHint') }}
    </n-modal>

    <!-- ── TEST EMAIL MODAL ── -->
    <n-modal
      v-model:show="testEmailModalOpen"
      :title="t('admin.email.testTitle')"
      preset="card"
      style="width:420px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form-item :label="t('admin.email.testTo')">
        <n-input v-model:value="testEmailAddress" :placeholder="t('admin.email.testToPlaceholder')" />
      </n-form-item>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="testEmailModalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="emailTesting" @click="sendTestEmail">
            {{ t('admin.email.sendTestBtn') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive, watch, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NTabs, NTabPane, NDataTable, NButton, NInput, NInputNumber, NIcon,
  NModal, NForm, NFormItem, NCheckbox, NTag, NSelect, NUpload, NSwitch,
  NCollapse, NCollapseItem,
  useMessage, type DataTableColumns, type UploadFileInfo,
} from 'naive-ui'
import { SearchOutline, SyncOutline, AddOutline, CreateOutline, TrashOutline, ShieldCheckmarkOutline } from '@vicons/ionicons5'
import { fetchUsers, changeUserRole, syncUsersFromKeycloak, type UserPublic } from '../api/users'
import { fetchLinks, createLink, updateLink, deleteLink, uploadLinkIcon, deleteLinkIcon, type ServiceLink, type CreateLinkDto } from '../api/links'
import { isSafeHttpUrl } from '../utils/url'
import { useBrandingStore, type BrandingSettings } from '../stores/branding'
import { api, apiUpload } from '../api'

const { t } = useI18n()
const message = useMessage()

const activeTab = ref('users')
const loaded = reactive<Record<string, boolean>>({})

async function ensureTabLoaded(tab: string) {
  if (loaded[tab]) return

  if (tab === 'users') {
    await Promise.all([loadUsers(), loadKcSyncStatus()])
  } else if (tab === 'links') {
    await loadLinks()
  } else if (tab === 'email') {
    await loadEmailSettings()
  } else if (tab === 'system') {
    await Promise.all([loadSystemSettings(), loadTlsStatus()])
  } else if (tab === 'keycloak') {
    await Promise.all([loadKcSettings(), loadKcSyncStatus()])
  } else if (tab === 'branding') {
    await loadBrandingForm()
  } else if (tab === 'modules') {
    await loadModules()
  }

  loaded[tab] = true
}

watch(activeTab, (tab) => {
  void ensureTabLoaded(tab)
}, { immediate: true })

onMounted(() => {
  void ensureTabLoaded(activeTab.value)
})

// ── Users ──────────────────────────────────────────────────────────────────
const users = ref<UserPublic[]>([])
const loadingUsers = ref(false)
const syncing = ref(false)
const userSearch = ref('')

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(u =>
    u.full_name.toLowerCase().includes(q) ||
    u.email.toLowerCase().includes(q) ||
    (u.department ?? '').toLowerCase().includes(q),
  )
})

const roleOptions = computed(() => [
  { label: t('admin.users.role.reader'), value: 'reader' },
  { label: t('admin.users.role.editor'), value: 'editor' },
  { label: t('admin.users.role.admin'), value: 'admin' },
])

const userColumns = computed<DataTableColumns<UserPublic>>(() => [
  {
    title: t('admin.users.columns.fullName'),
    key: 'full_name',
    sorter: 'default',
    ellipsis: { tooltip: true },
  },
  {
    title: t('admin.users.columns.email'),
    key: 'email',
    ellipsis: { tooltip: true },
  },
  {
    title: t('admin.users.columns.department'),
    key: 'department',
    ellipsis: { tooltip: true },
    render: (row) => row.department ?? '—',
  },
  {
    title: t('admin.users.columns.role'),
    key: 'role',
    width: 160,
    render: (row) =>
      h(NSelect, {
        value: row.role,
        options: roleOptions.value,
        size: 'small',
        style: 'width:140px',
        onUpdateValue: (val: string) => handleRoleChange(row, val),
      }),
  },
  {
    title: t('admin.users.columns.authSource'),
    key: 'auth_source',
    width: 120,
    render: (row) =>
      h(NTag, { size: 'small', type: (row as any).auth_source === 'local' ? 'warning' : 'info', bordered: false },
        { default: () => (row as any).auth_source === 'local' ? 'Local' : 'SSO' }),
  },
])

async function loadUsers() {
  loadingUsers.value = true
  try {
    const res = await fetchUsers({ page_size: 300 })
    users.value = res.items
  } catch {
    message.error(t('errors.generic'))
  } finally {
    loadingUsers.value = false
  }
}

async function handleRoleChange(user: UserPublic, role: string) {
  try {
    const updated = await changeUserRole(user.id, role)
    const idx = users.value.findIndex(u => u.id === user.id)
    if (idx !== -1) users.value[idx] = { ...users.value[idx], role: updated.role }
    message.success(t('admin.users.roleChanged'))
  } catch {
    message.error(t('errors.generic'))
  }
}

async function syncUsers() {
  syncing.value = true
  try {
    await syncUsersFromKeycloak()
    message.success(t('admin.users.syncOk'))
    await Promise.all([loadUsers(), loadKcSyncStatus()])
  } catch {
    message.error(t('errors.generic'))
  } finally {
    syncing.value = false
  }
}

// ── Links ──────────────────────────────────────────────────────────────────
const links = ref<ServiceLink[]>([])
const loadingLinks = ref(false)
const linkSearch = ref('')

const filteredLinks = computed(() => {
  const q = linkSearch.value.trim().toLowerCase()
  if (!q) return links.value
  return links.value.filter(l =>
    l.title.toLowerCase().includes(q) ||
    l.url.toLowerCase().includes(q) ||
    (l.category ?? '').toLowerCase().includes(q),
  )
})

const linkModalOpen = ref(false)
const savingLink = ref(false)
const editingLink = ref<ServiceLink | null>(null)
const linkFormRef = ref()

const iconFile = ref<File | null>(null)
const iconPreview = ref<string | null>(null)
const iconRemoved = ref(false)

function onIconFileChange({ file }: { file: UploadFileInfo }) {
  if (file.file) {
    if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
    iconFile.value = file.file
    iconPreview.value = URL.createObjectURL(file.file)
    iconRemoved.value = false
  }
}

function removeIcon() {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
  iconFile.value = null
  iconPreview.value = null
  iconRemoved.value = true
}

function resetIconState() {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
  iconFile.value = null
  iconPreview.value = null
  iconRemoved.value = false
}

const emptyLinkForm = (): CreateLinkDto & { id?: string } => ({
  title: '',
  url: '',
  description: null,
  category: null,
  sort_order: 0,
  supports_sso: false,
  is_active: true,
})

const linkForm = ref(emptyLinkForm())

const linkRules = computed(() => ({
  title: [{ required: true, message: t('admin.links.form.required'), trigger: 'blur' }],
  url: [
    { required: true, message: t('admin.links.form.required'), trigger: 'blur' },
    {
      validator: (_: unknown, value: string) => isSafeHttpUrl(value),
      message: t('admin.links.form.invalidUrl'),
      trigger: 'blur',
    },
  ],
}))

const deleteConfirmOpen = ref(false)
const deletingLink = ref<ServiceLink | null>(null)

const linkColumns = computed<DataTableColumns<ServiceLink>>(() => [
  {
    title: '',
    key: 'icon',
    width: 44,
    align: 'center',
    render: (row) =>
      row.icon_url
        ? h('img', { src: row.icon_url, style: 'width:24px;height:24px;object-fit:contain;vertical-align:middle', alt: '' })
        : null,
  },
  {
    title: t('admin.links.columns.title'),
    key: 'title',
    sorter: 'default',
    ellipsis: { tooltip: true },
  },
  {
    title: t('admin.links.columns.url'),
    key: 'url',
    ellipsis: { tooltip: true },
    render: (row) => h('span', { style: 'font-size:12px;color:var(--color-text-muted)' }, row.url),
  },
  {
    title: t('admin.links.columns.category'),
    key: 'category',
    width: 130,
    render: (row) => row.category ?? '—',
  },
  {
    title: t('admin.links.columns.sso'),
    key: 'supports_sso',
    width: 70,
    align: 'center',
    render: (row) =>
      row.supports_sso
        ? h(NIcon, { color: 'var(--color-brand-sky)', size: 18 }, { default: () => h(ShieldCheckmarkOutline) })
        : h('span', { style: 'color:var(--color-text-subtle)' }, '—'),
  },
  {
    title: t('admin.links.columns.active'),
    key: 'is_active',
    width: 90,
    align: 'center',
    render: (row) =>
      h(NTag, { size: 'small', type: row.is_active ? 'success' : 'default', bordered: false },
        { default: () => row.is_active ? t('common.yes') : t('common.no') }),
  },
  {
    title: t('admin.links.columns.actions'),
    key: 'actions',
    width: 100,
    align: 'center',
    render: (row) =>
      h('div', { style: 'display:flex;gap:6px;justify-content:center' }, [
        h(NButton, {
          size: 'small', quaternary: true, circle: true,
          title: t('common.edit'),
          onClick: () => openEditLink(row),
        }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) }),
        h(NButton, {
          size: 'small', quaternary: true, circle: true, type: 'error',
          title: t('common.delete'),
          onClick: () => openDeleteLink(row),
        }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
      ]),
  },
])

async function loadLinks() {
  loadingLinks.value = true
  try {
    const res = await fetchLinks({ include_inactive: true })
    links.value = res.items
  } catch {
    message.error(t('errors.generic'))
  } finally {
    loadingLinks.value = false
  }
}

function openAddLink() {
  editingLink.value = null
  linkForm.value = emptyLinkForm()
  resetIconState()
  linkModalOpen.value = true
}

function openEditLink(link: ServiceLink) {
  editingLink.value = link
  linkForm.value = {
    title: link.title,
    url: link.url,
    description: link.description,
    category: link.category,
    sort_order: link.sort_order,
    supports_sso: link.supports_sso,
    is_active: link.is_active,
  }
  resetIconState()
  linkModalOpen.value = true
}

function openDeleteLink(link: ServiceLink) {
  deletingLink.value = link
  deleteConfirmOpen.value = true
}

async function submitLink() {
  try {
    await linkFormRef.value?.validate()
  } catch {
    return
  }
  savingLink.value = true
  try {
    const dto: CreateLinkDto = {
      title: linkForm.value.title,
      url: linkForm.value.url,
      description: linkForm.value.description || null,
      category: linkForm.value.category || null,
      sort_order: linkForm.value.sort_order ?? 0,
      supports_sso: linkForm.value.supports_sso,
      is_active: linkForm.value.is_active,
    }

    let saved: ServiceLink
    if (editingLink.value) {
      saved = await updateLink(editingLink.value.id, dto)
      const idx = links.value.findIndex(l => l.id === editingLink.value!.id)
      if (idx !== -1) links.value[idx] = saved
    } else {
      saved = await createLink(dto)
      links.value.unshift(saved)
    }

    if (iconFile.value) {
      const withIcon = await uploadLinkIcon(saved.id, iconFile.value)
      const idx = links.value.findIndex(l => l.id === saved.id)
      if (idx !== -1) links.value[idx] = withIcon
    } else if (iconRemoved.value && editingLink.value?.icon_url) {
      await deleteLinkIcon(saved.id)
      const idx = links.value.findIndex(l => l.id === saved.id)
      if (idx !== -1) links.value[idx] = { ...links.value[idx], icon_url: null }
    }

    message.success(t('admin.links.saved'))
    linkModalOpen.value = false
  } catch {
    message.error(t('errors.generic'))
  } finally {
    savingLink.value = false
  }
}

async function confirmDelete() {
  if (!deletingLink.value) return
  try {
    await deleteLink(deletingLink.value.id)
    links.value = links.value.filter(l => l.id !== deletingLink.value!.id)
    message.success(t('admin.links.deleted'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    deletingLink.value = null
  }
}

// ── Branding ────────────────────────────────────────────────────────────────
const currentLogoUrl = ref<string | null>(null)
const logoInputRef = ref<HTMLInputElement | null>(null)
const logoUploading = ref(false)
const logoResetting = ref(false)

async function onLogoFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  if (file.size > 2 * 1024 * 1024) {
    message.error(t('admin.branding.logoTooBig'))
    return
  }

  logoUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await apiUpload('/admin/branding/logo', fd)
    currentLogoUrl.value = `/api/v1/branding/logo?t=${Date.now()}`
    window.dispatchEvent(new CustomEvent('logo-updated'))
    message.success(t('admin.branding.logoUploaded'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    logoUploading.value = false
  }
}

async function onLogoReset() {
  logoResetting.value = true
  try {
    await api('/admin/branding/logo', { method: 'DELETE' })
    currentLogoUrl.value = null
    window.dispatchEvent(new CustomEvent('logo-updated'))
    message.success(t('admin.branding.logoReset'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    logoResetting.value = false
  }
}

// ── Favicon ──────────────────────────────────────────────────────────────────
const currentFaviconUrl = ref<string | null>(null)
const faviconInputRef = ref<HTMLInputElement | null>(null)
const faviconUploading = ref(false)
const faviconResetting = ref(false)



async function onFaviconFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  if (file.size > 2 * 1024 * 1024) { message.error(t('admin.branding.logoTooBig')); return }
  faviconUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await apiUpload('/admin/branding/favicon', fd)
    currentFaviconUrl.value = `/api/v1/branding/favicon?t=${Date.now()}`
    brandingStore.load()
    message.success(t('admin.branding.faviconUploaded'))
  } catch { message.error(t('errors.generic')) }
  finally { faviconUploading.value = false }
}

async function onFaviconReset() {
  faviconResetting.value = true
  try {
    await api('/admin/branding/favicon', { method: 'DELETE' })
    currentFaviconUrl.value = null
    message.success(t('admin.branding.faviconReset'))
  } catch { message.error(t('errors.generic')) }
  finally { faviconResetting.value = false }
}

// ── Login background ──────────────────────────────────────────────────────────
const currentLoginBgUrl = ref<string | null>(null)
const loginBgInputRef = ref<HTMLInputElement | null>(null)
const loginBgUploading = ref(false)
const loginBgResetting = ref(false)



async function onLoginBgFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  if (file.size > 2 * 1024 * 1024) { message.error(t('admin.branding.logoTooBig')); return }
  loginBgUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await apiUpload('/admin/branding/login-bg', fd)
    currentLoginBgUrl.value = `/api/v1/branding/login-bg?t=${Date.now()}`
    message.success(t('admin.branding.loginBgUploaded'))
  } catch { message.error(t('errors.generic')) }
  finally { loginBgUploading.value = false }
}

async function onLoginBgReset() {
  loginBgResetting.value = true
  try {
    await api('/admin/branding/login-bg', { method: 'DELETE' })
    currentLoginBgUrl.value = null
    message.success(t('admin.branding.loginBgReset'))
  } catch { message.error(t('errors.generic')) }
  finally { loginBgResetting.value = false }
}

// ── System Settings ───────────────────────────────────────────────────────────

interface SysSettingsOut {
  portal_base_url: string
  nextcloud_url: string
  nc_user_id_field: string
  nc_service_app_password_set: boolean
  max_upload_size_mb: number
  allowed_cidr: string
  prometheus_metrics_enabled: boolean
  news_attachment_max_size_mb: number
  kb_media_max_size_mb: number
  kb_attachment_max_size_mb: number
  log_level: string
  timezone: string
  sentry_dsn_set: boolean
  log_force_json: boolean | null
  log_slow_request_ms: number
  arq_max_jobs: number
  photo_gallery_url: string
  video_gallery_url: string
}

interface NextcloudModuleOut {
  enabled: boolean
}

interface PhotosModuleOut {
  enabled: boolean
  widget_limit: number
  max_size_mb: number
  allowed_mime: string[]
  strip_gps: boolean
}

interface AllModulesOut {
  nextcloud: NextcloudModuleOut
  photos: PhotosModuleOut
}

const logLevelOptions = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].map(v => ({ label: v, value: v }))

const logForceJsonOptions = computed(() => [
  { label: t('admin.system.logForceJsonAuto'), value: 'null' },
  { label: t('admin.system.logForceJsonJson'), value: 'true' },
  { label: t('admin.system.logForceJsonText'), value: 'false' },
])

function logForceJsonFromStr(v: string): boolean | null {
  if (v === 'true') return true
  if (v === 'false') return false
  return null
}

function logForceJsonToStr(v: boolean | null): string {
  if (v === true) return 'true'
  if (v === false) return 'false'
  return 'null'
}

interface TlsStatus {
  cert_exists: boolean
  key_exists: boolean
  cert_expires_at: string | null
  cert_subject: string | null
}

const sysSettings = ref<SysSettingsOut | null>(null)
const tlsStatus = ref<TlsStatus | null>(null)
const sysSaving = ref(false)
const sysNginxReloading = ref(false)
const ncTesting = ref(false)
const ncTestResult = ref<{ ok: boolean; details?: string } | null>(null)

const sysForm = ref({
  portal_base_url: '',
  nextcloud_url: '',
  nc_user_id_field: '',
  nc_service_password: '',
  max_upload_size_mb: 100,
  allowed_cidr: '',
  prometheus_metrics_enabled: true,
  news_attachment_max_size_mb: 50,
  kb_media_max_size_mb: 20,
  kb_attachment_max_size_mb: 50,
  log_level: 'INFO',
  timezone: 'Europe/Moscow',
  sentry_dsn: '',
  log_force_json: 'null',
  log_slow_request_ms: 1000,
  arq_max_jobs: 10,
  photo_gallery_url: '',
  video_gallery_url: '',
})

const sysLoadError = ref(false)
const tlsLoadError = ref(false)

async function loadSystemSettings() {
  try {
    const data = await api<SysSettingsOut>('/admin/system/settings')
    sysSettings.value = data
    sysForm.value.portal_base_url = data.portal_base_url
    sysForm.value.nextcloud_url = data.nextcloud_url
    sysForm.value.nc_user_id_field = data.nc_user_id_field
    sysForm.value.nc_service_password = ''
    sysForm.value.max_upload_size_mb = data.max_upload_size_mb
    sysForm.value.allowed_cidr = data.allowed_cidr
    sysForm.value.prometheus_metrics_enabled = data.prometheus_metrics_enabled
    sysForm.value.news_attachment_max_size_mb = data.news_attachment_max_size_mb
    sysForm.value.kb_media_max_size_mb = data.kb_media_max_size_mb
    sysForm.value.kb_attachment_max_size_mb = data.kb_attachment_max_size_mb
    sysForm.value.log_level = data.log_level
    sysForm.value.timezone = data.timezone
    sysForm.value.sentry_dsn = ''
    sysForm.value.log_force_json = logForceJsonToStr(data.log_force_json)
    sysForm.value.log_slow_request_ms = data.log_slow_request_ms
    sysForm.value.arq_max_jobs = data.arq_max_jobs
    sysForm.value.photo_gallery_url = data.photo_gallery_url
    sysForm.value.video_gallery_url = data.video_gallery_url
    sysLoadError.value = false
  } catch {
    sysLoadError.value = true
    message.error(t('errors.generic'))
  }
}

async function loadTlsStatus() {
  try {
    tlsStatus.value = await api<TlsStatus>('/admin/system/tls/status')
    tlsLoadError.value = false
  } catch {
    tlsLoadError.value = true
  }
}

async function saveSystemSettings() {
  if (sysLoadError.value) {
    message.error(t('admin.system.loadFailedGuard'))
    return
  }
  sysSaving.value = true
  try {
    const body = {
      portal_base_url: sysForm.value.portal_base_url,
      nextcloud_url: sysForm.value.nextcloud_url,
      nc_user_id_field: sysForm.value.nc_user_id_field,
      nc_service_app_password: sysForm.value.nc_service_password || null,
      max_upload_size_mb: sysForm.value.max_upload_size_mb,
      allowed_cidr: sysForm.value.allowed_cidr,
      prometheus_metrics_enabled: sysForm.value.prometheus_metrics_enabled,
      news_attachment_max_size_mb: sysForm.value.news_attachment_max_size_mb,
      kb_media_max_size_mb: sysForm.value.kb_media_max_size_mb,
      kb_attachment_max_size_mb: sysForm.value.kb_attachment_max_size_mb,
      log_level: sysForm.value.log_level,
      timezone: sysForm.value.timezone,
      sentry_dsn: sysForm.value.sentry_dsn || null,
      log_force_json: logForceJsonFromStr(sysForm.value.log_force_json),
      log_slow_request_ms: sysForm.value.log_slow_request_ms,
      arq_max_jobs: sysForm.value.arq_max_jobs,
      photo_gallery_url: sysForm.value.photo_gallery_url,
      video_gallery_url: sysForm.value.video_gallery_url,
    }
    const data = await api<SysSettingsOut>('/admin/system/settings', { method: 'PUT', body })
    sysSettings.value = data
    sysForm.value.nc_service_password = ''
    sysForm.value.sentry_dsn = ''
    message.success(t('admin.system.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    sysSaving.value = false
  }
}

async function reloadNginx() {
  sysNginxReloading.value = true
  try {
    await api('/admin/system/nginx/reload', { method: 'POST' })
    message.success(t('admin.system.nginxReloaded'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    sysNginxReloading.value = false
  }
}

interface NcStatusOut {
  ok: boolean
  configured: boolean
  server_reachable: boolean
  nc_version: string | null
  auth_ok: boolean
  webdav_ok: boolean
  details: string | null
}

async function testNcConnection() {
  ncTesting.value = true
  ncTestResult.value = null
  try {
    const res = await api<NcStatusOut>('/admin/system/nextcloud/status')
    const parts: string[] = []
    if (res.nc_version) parts.push(`Nextcloud ${res.nc_version}`)
    if (res.server_reachable && !res.auth_ok) parts.push(t('admin.system.ncTestServerOk'))
    if (res.auth_ok) parts.push(t('admin.system.ncTestAuthOk'))
    if (res.details) parts.push(res.details)
    ncTestResult.value = { ok: res.ok, details: parts.join(' · ') || undefined }
  } catch (e: unknown) {
    ncTestResult.value = { ok: false, details: String(e) }
  } finally {
    ncTesting.value = false
  }
}

async function uploadTlsFile(type: 'cert' | 'key', info: { file: UploadFileInfo }) {
  const file = info.file?.file
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  try {
    await apiUpload(`/admin/system/tls/${type}`, form)
    message.success(t('admin.system.tlsUploaded'))
    await loadTlsStatus()
  } catch {
    message.error(t('errors.generic'))
  }
}

async function deleteTlsFile(type: 'cert' | 'key') {
  try {
    await api(`/admin/system/tls/${type}`, { method: 'DELETE' })
    message.success(t('admin.system.tlsDeleted'))
    await loadTlsStatus()
  } catch {
    message.error(t('errors.generic'))
  }
}

// ── Keycloak ──────────────────────────────────────────────────────────────────

interface KcSettingsOut {
  keycloak_url: string
  keycloak_realm: string
  oidc_client_id: string
  oidc_client_secret_set: boolean
  sync_client_id: string
  sync_client_secret_set: boolean
}

interface KcSyncStatus {
  last_run_at: string | null
  last_count: number | null
  last_status: string | null
}

interface KcTestResult {
  ok: boolean
  details?: string
}

const kcSettings = ref<KcSettingsOut | null>(null)
const kcSyncStatus = ref<KcSyncStatus | null>(null)
const kcSaving = ref(false)
const kcTestingOidc = ref(false)
const kcTestingSync = ref(false)
const kcOidcTestResult = ref<KcTestResult | null>(null)
const kcSyncTestResult = ref<KcTestResult | null>(null)

const kcForm = ref({
  keycloak_url: '',
  keycloak_realm: '',
  oidc_client_id: '',
  oidc_client_secret: '',
  sync_client_id: '',
  sync_client_secret: '',
})

const kcLoadError = ref(false)

async function loadKcSettings() {
  try {
    const data = await api<KcSettingsOut>('/admin/keycloak/settings')
    kcSettings.value = data
    kcForm.value.keycloak_url = data.keycloak_url
    kcForm.value.keycloak_realm = data.keycloak_realm
    kcForm.value.oidc_client_id = data.oidc_client_id
    kcForm.value.oidc_client_secret = ''
    kcForm.value.sync_client_id = data.sync_client_id
    kcForm.value.sync_client_secret = ''
    kcLoadError.value = false
  } catch {
    kcLoadError.value = true
    message.error(t('errors.generic'))
  }
}

async function loadKcSyncStatus() {
  try {
    kcSyncStatus.value = await api<KcSyncStatus>('/admin/keycloak/sync/status')
  } catch {
  }
}

async function saveKcSettings() {
  if (kcLoadError.value) {
    message.error(t('admin.keycloak.loadFailedGuard'))
    return
  }
  kcSaving.value = true
  try {
    // Semantics: null = keep existing, "" = clear, non-empty = update
    // Clearing sync_client_id is treated as intent to disconnect → also clear secret.
    const syncIdEmpty = kcForm.value.sync_client_id.trim() === ''
    const body: Record<string, string | null> = {
      keycloak_url: kcForm.value.keycloak_url,
      keycloak_realm: kcForm.value.keycloak_realm,
      oidc_client_id: kcForm.value.oidc_client_id,
      oidc_client_secret: kcForm.value.oidc_client_secret || null,
      sync_client_id: kcForm.value.sync_client_id,
      sync_client_secret: syncIdEmpty ? '' : (kcForm.value.sync_client_secret || null),
    }
    const data = await api<KcSettingsOut>('/admin/keycloak/settings', { method: 'PUT', body })
    kcSettings.value = data
    kcForm.value.oidc_client_secret = ''
    kcForm.value.sync_client_secret = ''
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
    const res = await api<Record<string, unknown>>('/admin/keycloak/test/sync', { method: 'POST' })
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

// ── Branding form (settings) ──────────────────────────────────────────────────
const brandingStore = useBrandingStore()
const brandingFormSaving = ref(false)
const brandingForm = ref<BrandingSettings>({ ...brandingStore.settings })

const bannerTypeOptions = computed(() => [
  { label: t('admin.branding.bannerTypeInfo'), value: 'info' },
  { label: t('admin.branding.bannerTypeWarning'), value: 'warning' },
  { label: t('admin.branding.bannerTypeError'), value: 'error' },
  { label: t('admin.branding.bannerTypeSuccess'), value: 'success' },
])

async function loadBrandingForm() {
  await brandingStore.load()
  brandingForm.value = { ...brandingStore.settings }
  currentLogoUrl.value = brandingStore.settings.has_logo ? `/api/v1/branding/logo?t=${Date.now()}` : null
  currentFaviconUrl.value = brandingStore.settings.has_favicon ? `/api/v1/branding/favicon?t=${Date.now()}` : null
  currentLoginBgUrl.value = brandingStore.settings.has_login_bg ? `/api/v1/branding/login-bg?t=${Date.now()}` : null
}

async function saveBrandingForm() {
  brandingFormSaving.value = true
  try {
    await brandingStore.save(brandingForm.value)
    message.success(t('admin.branding.settingsSaved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    brandingFormSaving.value = false
  }
}

// ── Modules ──────────────────────────────────────────────────────────────────

const modulesSettings = ref<AllModulesOut | null>(null)
const modulesLoadError = ref(false)

const modulesForm = ref({
  nextcloud: {
    enabled: false,
  },
  photos: {
    enabled: true,
    widget_limit: 8,
    max_size_mb: 50,
    allowed_mime: 'image/jpeg,image/png,image/webp,image/heic,image/heif,image/gif',
    strip_gps: true,
  },
})

const modulesPhotosSaving = ref(false)
const modulesNextcloudSaving = ref(false)
const ncConnectionSaving = ref(false)

async function loadModules() {
  try {
    const data = await api<AllModulesOut>('/admin/modules')
    modulesSettings.value = data
    modulesForm.value.nextcloud.enabled = data.nextcloud.enabled
    if (data.photos) {
      modulesForm.value.photos.enabled = data.photos.enabled
      modulesForm.value.photos.widget_limit = data.photos.widget_limit
      modulesForm.value.photos.max_size_mb = data.photos.max_size_mb
      modulesForm.value.photos.allowed_mime = (data.photos.allowed_mime || []).join(',')
      modulesForm.value.photos.strip_gps = data.photos.strip_gps
    }
    modulesLoadError.value = false
  } catch {
    modulesLoadError.value = true
    message.error(t('errors.generic'))
  }
}

async function saveNextcloudModule() {
  if (modulesLoadError.value) { message.error(t('admin.modules.loadFailedGuard')); return }
  modulesNextcloudSaving.value = true
  try {
    const data = await api<{ enabled: boolean }>('/admin/modules/nextcloud', {
      method: 'PUT',
      body: { enabled: modulesForm.value.nextcloud.enabled },
    })
    if (modulesSettings.value) modulesSettings.value.nextcloud = data
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    modulesNextcloudSaving.value = false
  }
}

async function saveNextcloudAll() {
  await saveNextcloudModule()
  if (modulesForm.value.nextcloud.enabled) {
    await saveNcConnectionSettings()
  }
}

async function saveNcConnectionSettings() {
  if (sysLoadError.value) { message.error(t('admin.system.loadFailedGuard')); return }
  ncConnectionSaving.value = true
  try {
    const body = {
      portal_base_url: sysForm.value.portal_base_url,
      nextcloud_url: sysForm.value.nextcloud_url,
      nc_user_id_field: sysForm.value.nc_user_id_field,
      nc_service_app_password: sysForm.value.nc_service_password || null,
      max_upload_size_mb: sysForm.value.max_upload_size_mb,
      allowed_cidr: sysForm.value.allowed_cidr,
      prometheus_metrics_enabled: sysForm.value.prometheus_metrics_enabled,
      news_attachment_max_size_mb: sysForm.value.news_attachment_max_size_mb,
      kb_media_max_size_mb: sysForm.value.kb_media_max_size_mb,
      kb_attachment_max_size_mb: sysForm.value.kb_attachment_max_size_mb,
      log_level: sysForm.value.log_level,
      timezone: sysForm.value.timezone,
      sentry_dsn: sysForm.value.sentry_dsn || null,
      log_force_json: logForceJsonFromStr(sysForm.value.log_force_json),
      log_slow_request_ms: sysForm.value.log_slow_request_ms,
      arq_max_jobs: sysForm.value.arq_max_jobs,
      photo_gallery_url: sysForm.value.photo_gallery_url,
      video_gallery_url: sysForm.value.video_gallery_url,
    }
    const data = await api<SysSettingsOut>('/admin/system/settings', { method: 'PUT', body })
    sysSettings.value = data
    sysForm.value.nc_service_password = ''
    message.success(t('admin.system.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    ncConnectionSaving.value = false
  }
}

async function savePhotosModule() {
  if (modulesLoadError.value) { message.error(t('admin.modules.loadFailedGuard')); return }
  modulesPhotosSaving.value = true
  try {
    const body = {
      enabled: modulesForm.value.photos.enabled,
      widget_limit: modulesForm.value.photos.widget_limit,
      max_size_mb: modulesForm.value.photos.max_size_mb,
      allowed_mime: modulesForm.value.photos.allowed_mime
        .split(',').map(s => s.trim()).filter(Boolean),
      strip_gps: modulesForm.value.photos.strip_gps,
    }
    const data = await api<PhotosModuleOut>('/admin/modules/photos', { method: 'PUT', body })
    if (modulesSettings.value) modulesSettings.value.photos = data
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    modulesPhotosSaving.value = false
  }
}

async function savePhotosModuleAndUrls() {
  await Promise.all([savePhotosModule(), saveSystemSettings()])
}

onUnmounted(() => {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
})

// ── Email ────────────────────────────────────────────────────────────────────
interface EmailFormType {
  host: string
  port: number
  from_address: string
  username: string
  password: string
  use_tls: boolean
  use_starttls: boolean
}

const emailForm = ref<EmailFormType>({
  host: '',
  port: 25,
  from_address: '',
  username: '',
  password: '',
  use_tls: false,
  use_starttls: false,
})
const emailPasswordSet = ref(false)
const emailSaving = ref(false)
const emailTesting = ref(false)
const testEmailModalOpen = ref(false)
const testEmailAddress = ref('')

const emailLoadError = ref(false)

async function loadEmailSettings() {
  try {
    const data = await api<{
      host: string; port: number; from_address: string; username: string
      password_set: boolean; use_tls: boolean; use_starttls: boolean
    }>('/admin/email-settings')
    emailForm.value = {
      host: data.host,
      port: data.port,
      from_address: data.from_address,
      username: data.username,
      password: '',
      use_tls: data.use_tls,
      use_starttls: data.use_starttls,
    }
    emailPasswordSet.value = data.password_set
    emailLoadError.value = false
  } catch {
    emailLoadError.value = true
    message.error(t('errors.generic'))
  }
}

async function saveEmailSettings() {
  if (emailLoadError.value) {
    message.error(t('admin.email.loadFailedGuard'))
    return
  }
  emailSaving.value = true
  try {
    const payload = {
      ...emailForm.value,
      password: emailForm.value.password || null,
    }
    const data = await api<{ host: string; port: number; from_address: string; username: string; password_set: boolean; use_tls: boolean; use_starttls: boolean }>(
      '/admin/email-settings',
      { method: 'PUT', body: payload },
    )
    emailPasswordSet.value = data.password_set
    emailForm.value.password = ''
    message.success(t('admin.email.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    emailSaving.value = false
  }
}

function openTestEmailModal() {
  testEmailModalOpen.value = true
}

async function sendTestEmail() {
  if (!testEmailAddress.value.trim()) {
    message.warning(t('admin.email.testToRequired'))
    return
  }
  emailTesting.value = true
  try {
    await api('/admin/email-settings/test', {
      method: 'POST',
      body: { to: testEmailAddress.value.trim() },
    })
    message.success(t('admin.email.testSent', { to: testEmailAddress.value }))
    testEmailModalOpen.value = false
  } catch {
    message.error(t('errors.generic'))
  } finally {
    emailTesting.value = false
  }
}
</script>

<style scoped>
.admin-wrap {
  max-width: 1280px;
  margin: 0 auto;
}
.page-head {
  margin-bottom: 20px;
}
.page-head__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text);
}

.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.data-table {
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}

.form-checks {
  display: flex;
  gap: 24px;
  margin-top: 4px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.icon-upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.icon-preview-wrap {
  position: relative;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
}

.icon-preview {
  width: 40px;
  height: 40px;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}

.icon-preview-remove {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 18px !important;
  height: 18px !important;
  min-width: 18px !important;
  font-size: 12px;
}

.branding-wrap {
  max-width: 640px;
  padding-top: 8px;
}

.branding-section {
  padding: 24px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}

.branding-section__title {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 4px;
}

.module-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.module-test-result {
  margin-top: 10px;
  padding: 8px 12px;
  font-size: 13px;
  border-radius: 6px;
  line-height: 1.4;
}
.module-test-result.ok {
  background: rgba(16, 185, 129, 0.08);
  color: #047857;
  border: 1px solid rgba(16, 185, 129, 0.3);
}
.module-test-result.err {
  background: rgba(239, 68, 68, 0.08);
  color: #b91c1c;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.branding-section__hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 20px;
}

.branding-logo-row {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.branding-logo-preview {
  width: 180px;
  height: 64px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}

.branding-logo-img {
  max-width: 160px;
  max-height: 52px;
  object-fit: contain;
}

.branding-logo-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.branding-logo-placeholder__text {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.logo-mark-preview {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-md);
  background: var(--gradient-hero);
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-mark-preview__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
}

.branding-logo-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.branding-favicon-preview {
  width: 32px;
  height: 32px;
  object-fit: contain;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  flex-shrink: 0;
}

.branding-loginbg-preview {
  width: 240px;
  height: 120px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  flex-shrink: 0;
}

.branding-loginbg-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.branding-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.branding-color-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.branding-color-input {
  width: 48px;
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px;
  cursor: pointer;
  background: none;
}

.branding-color-swatch {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  flex-shrink: 0;
}

.branding-section + .branding-section {
  margin-top: 16px;
}

.email-row-2 {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.email-switches {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.email-switch-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-right: 16px;
}

.email-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}
.kc-test-result {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}
.kc-test-result--ok {
  background: rgba(24, 160, 88, 0.1);
  border: 1px solid rgba(24, 160, 88, 0.3);
  color: #18a058;
}
.kc-test-result--fail {
  background: rgba(208, 48, 80, 0.08);
  border: 1px solid rgba(208, 48, 80, 0.25);
  color: #d03050;
}
.kc-test-result__title {
  font-weight: 600;
}
.kc-test-result__details {
  margin-top: 4px;
  font-size: 12px;
  opacity: 0.85;
  word-break: break-all;
}
.kc-sync-status {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.kc-sync-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
}
.kc-sync-label {
  min-width: 200px;
  color: var(--color-text-secondary, #666);
}
.kc-sync-value {
  font-weight: 500;
}
.kc-guide-list {
  padding-left: 20px;
  margin: 8px 0;
  line-height: 1.8;
  font-size: 13px;
}
.kc-guide-note {
  margin-top: 12px;
  padding: 10px 14px;
  background: rgba(37, 99, 235, 0.07);
  border-radius: 6px;
  font-size: 13px;
}
.kc-guide-note p {
  margin: 4px 0 0;
  line-height: 1.6;
}
.tls-status-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.tls-meta {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>
