<template>
  <div class="branding-wrap">
    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.branding.logoTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.branding.logoHint') }}
      </div>
      <div class="branding-logo-row">
        <div class="branding-logo-preview">
          <img
            v-if="currentLogoUrl"
            :src="currentLogoUrl"
            class="branding-logo-img"
            alt="Logo"
          >
          <div
            v-else
            class="branding-logo-placeholder"
          >
            <div class="logo-mark-preview">
              <span class="logo-mark-preview__dot" />
            </div>
            <span class="branding-logo-placeholder__text">{{ t('admin.branding.logoDefault') }}</span>
          </div>
        </div>
        <div class="branding-logo-actions">
          <input
            ref="logoInputRef"
            type="file"
            accept="image/png,image/jpeg,image/svg+xml,image/webp"
            style="display:none"
            aria-label="Upload logo"
            @change="onLogoFileChange"
          >
          <n-button
            type="primary"
            :loading="logoUploading"
            @click="logoInputRef?.click()"
          >
            {{ t('admin.branding.uploadLogo') }}
          </n-button>
          <n-button
            v-if="currentLogoUrl"
            :loading="logoResetting"
            @click="onLogoReset"
          >
            {{ t('admin.branding.resetLogo') }}
          </n-button>
        </div>
      </div>
      <n-checkbox
        v-model:checked="brandingForm.logo_hidden"
        style="margin-top:12px"
        @update:checked="saveBrandingForm"
      >
        {{ t('admin.branding.logoHidden') }}
      </n-checkbox>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.branding.faviconTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.branding.faviconHint') }}
      </div>
      <div
        class="branding-logo-actions"
        style="flex-direction:row;align-items:center;gap:12px"
      >
        <img
          v-if="currentFaviconUrl"
          :src="currentFaviconUrl"
          class="branding-favicon-preview"
          alt="Favicon"
        >
        <input
          ref="faviconInputRef"
          type="file"
          accept="image/png,image/jpeg,image/svg+xml,image/webp,image/x-icon"
          style="display:none"
          aria-label="Upload favicon"
          @change="onFaviconFileChange"
        >
        <n-button
          type="primary"
          size="small"
          :loading="faviconUploading"
          @click="faviconInputRef?.click()"
        >
          {{ t('admin.branding.uploadFavicon') }}
        </n-button>
        <n-button
          v-if="currentFaviconUrl"
          size="small"
          :loading="faviconResetting"
          @click="onFaviconReset"
        >
          {{ t('admin.branding.resetFavicon') }}
        </n-button>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.branding.loginBgTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.branding.loginBgHint') }}
      </div>
      <div class="branding-logo-row">
        <div
          v-if="currentLoginBgUrl"
          class="branding-loginbg-preview"
        >
          <img
            :src="currentLoginBgUrl"
            alt="Login BG"
            class="branding-loginbg-img"
          >
        </div>
        <div class="branding-logo-actions">
          <input
            ref="loginBgInputRef"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            style="display:none"
            aria-label="Upload login background"
            @change="onLoginBgFileChange"
          >
          <n-button
            type="primary"
            size="small"
            :loading="loginBgUploading"
            @click="loginBgInputRef?.click()"
          >
            {{ t('admin.branding.uploadLoginBg') }}
          </n-button>
          <n-button
            v-if="currentLoginBgUrl"
            size="small"
            :loading="loginBgResetting"
            @click="onLoginBgReset"
          >
            {{ t('admin.branding.resetLoginBg') }}
          </n-button>
        </div>
      </div>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.branding.generalTitle') }}
      </div>
      <div class="branding-fields">
        <n-form-item
          :label="t('admin.branding.portalName')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="brandingForm.portal_name"
            :placeholder="t('admin.branding.portalNamePlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.branding.portalTagline')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="brandingForm.portal_tagline"
            :placeholder="t('admin.branding.portalTaglinePlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.branding.accentColor')"
          style="margin-bottom:0"
        >
          <div class="branding-color-row">
            <input
              v-model="brandingForm.accent_color"
              type="color"
              class="branding-color-input"
              aria-label="Accent color"
            >
            <n-input
              v-model:value="brandingForm.accent_color"
              style="width:120px;font-family:monospace"
            />
            <div
              class="branding-color-swatch"
              :style="`background:${brandingForm.accent_color}`"
            />
          </div>
        </n-form-item>
        <n-form-item
          :label="t('admin.branding.welcomeSubtitle')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="brandingForm.welcome_subtitle"
            type="textarea"
            :rows="2"
            :placeholder="t('admin.branding.welcomeSubtitlePlaceholder')"
          />
        </n-form-item>
      </div>
      <n-button
        type="primary"
        :loading="brandingFormSaving"
        style="margin-top:16px"
        @click="saveBrandingForm"
      >
        {{ t('common.save') }}
      </n-button>
    </div>

    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.branding.bannerTitle') }}
      </div>
      <div class="branding-fields">
        <n-form-item
          :label="t('admin.branding.bannerEnabled')"
          style="margin-bottom:0"
        >
          <n-switch v-model:value="brandingForm.banner_enabled" />
        </n-form-item>
        <n-form-item
          :label="t('admin.branding.bannerText')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="brandingForm.banner_text"
            type="textarea"
            :rows="2"
            :placeholder="t('admin.branding.bannerTextPlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.branding.bannerType')"
          style="margin-bottom:0"
        >
          <n-select
            v-model:value="brandingForm.banner_type"
            :options="bannerTypeOptions"
            style="width:200px"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.branding.bannerExpires')"
          style="margin-bottom:0"
        >
          <n-input
            v-model:value="brandingForm.banner_expires_at"
            :placeholder="t('admin.branding.bannerExpiresPlaceholder')"
            clearable
            style="width:220px"
          />
          <span style="margin-left:8px;font-size:12px;color:var(--color-text-muted)">{{ t('admin.branding.bannerExpiresHint') }}</span>
        </n-form-item>
      </div>
      <n-button
        type="primary"
        :loading="brandingFormSaving"
        style="margin-top:16px"
        @click="saveBrandingForm"
      >
        {{ t('common.save') }}
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NFormItem, NSwitch, NSelect, NCheckbox, useMessage } from 'naive-ui'
import { useBrandingStore, type BrandingSettings, type BrandingAsset } from '../../../stores/branding'

const { t } = useI18n()
const message = useMessage()
const brandingStore = useBrandingStore()

const BRANDING_MAX_SIZE = 2 * 1024 * 1024

const logoInputRef = ref<HTMLInputElement | null>(null)
const logoUploading = ref(false)
const logoResetting = ref(false)

const faviconInputRef = ref<HTMLInputElement | null>(null)
const faviconUploading = ref(false)
const faviconResetting = ref(false)

const loginBgInputRef = ref<HTMLInputElement | null>(null)
const loginBgUploading = ref(false)
const loginBgResetting = ref(false)

const currentLogoUrl = computed(() => brandingStore.assetUrl('logo'))
const currentFaviconUrl = computed(() => brandingStore.assetUrl('favicon'))
const currentLoginBgUrl = computed(() => brandingStore.assetUrl('login-bg'))

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

async function pickAndUpload(
  e: Event,
  kind: BrandingAsset,
  busy: { value: boolean },
  successKey: string,
) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  if (file.size > BRANDING_MAX_SIZE) { message.error(t('admin.branding.logoTooBig')); return }
  busy.value = true
  try {
    await brandingStore.uploadAsset(kind, file)
    message.success(t(successKey))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    busy.value = false
  }
}

async function resetAsset(
  kind: BrandingAsset,
  busy: { value: boolean },
  successKey: string,
) {
  busy.value = true
  try {
    await brandingStore.resetAsset(kind)
    message.success(t(successKey))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    busy.value = false
  }
}

const onLogoFileChange = (e: Event) => pickAndUpload(e, 'logo', logoUploading, 'admin.branding.logoUploaded')
const onLogoReset = () => resetAsset('logo', logoResetting, 'admin.branding.logoReset')
const onFaviconFileChange = (e: Event) => pickAndUpload(e, 'favicon', faviconUploading, 'admin.branding.faviconUploaded')
const onFaviconReset = () => resetAsset('favicon', faviconResetting, 'admin.branding.faviconReset')
const onLoginBgFileChange = (e: Event) => pickAndUpload(e, 'login-bg', loginBgUploading, 'admin.branding.loginBgUploaded')
const onLoginBgReset = () => resetAsset('login-bg', loginBgResetting, 'admin.branding.loginBgReset')

onMounted(() => {
  void loadBrandingForm()
})
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
