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
        {{ t('admin.branding.heroBgTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.branding.heroBgHint') }}
      </div>

      <!-- Час-границы слотов (hero_morning_hour / hero_day_hour / hero_evening_hour) -->
      <div
        class="branding-fields"
        style="margin-bottom:16px"
      >
        <n-form-item
          :label="t('admin.branding.heroBgMorningHour')"
          style="margin-bottom:0"
        >
          <n-input-number
            v-model:value="brandingForm.hero_morning_hour"
            :min="0"
            :max="23"
            style="width:120px"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.branding.heroBgDayHour')"
          style="margin-bottom:0"
        >
          <n-input-number
            v-model:value="brandingForm.hero_day_hour"
            :min="0"
            :max="23"
            style="width:120px"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.branding.heroBgEveningHour')"
          style="margin-bottom:0"
        >
          <n-input-number
            v-model:value="brandingForm.hero_evening_hour"
            :min="0"
            :max="23"
            style="width:120px"
          />
        </n-form-item>
      </div>

      <!-- Три аплоада: утро / день / вечер -->
      <div class="hero-bg-grid">
        <div
          v-for="slot in heroBgSlots"
          :key="slot.kind"
          class="hero-bg-tile"
        >
          <div class="hero-bg-tile__label">
            {{ t(slot.labelKey) }}
          </div>
          <div class="hero-bg-tile__preview">
            <img
              v-if="brandingStore.assetUrl(slot.kind)"
              :src="brandingStore.assetUrl(slot.kind)!"
              :alt="t(slot.labelKey)"
              class="hero-bg-tile__img"
            >
            <div
              v-else
              class="hero-bg-tile__placeholder"
            />
          </div>
          <div class="hero-bg-tile__actions">
            <input
              :ref="(el) => setHeroInputRef(slot.kind, el as HTMLInputElement | null)"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              style="display:none"
              :aria-label="`Upload ${slot.kind}`"
              @change="onHeroBgFileChange($event, slot.kind)"
            >
            <n-button
              size="small"
              type="primary"
              :loading="heroBgBusy[slot.kind]"
              @click="heroInputRefs[slot.kind]?.click()"
            >
              {{ t('admin.branding.heroBgUpload') }}
            </n-button>
            <n-button
              v-if="brandingStore.assetUrl(slot.kind)"
              size="small"
              :loading="heroBgResetBusy[slot.kind]"
              @click="onHeroBgReset(slot.kind)"
            >
              {{ t('admin.branding.heroBgReset') }}
            </n-button>
          </div>
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
          :label="t('admin.branding.heroSubtitleMode')"
          style="margin-bottom:0"
        >
          <n-select
            v-model:value="brandingForm.hero_subtitle_mode"
            :options="heroSubtitleModeOptions"
            style="width:240px"
          />
        </n-form-item>
        <n-form-item
          v-if="brandingForm.hero_subtitle_mode === 'custom'"
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
import { ref, computed, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NInputNumber, NFormItem, NSwitch, NSelect, NCheckbox, useMessage } from 'naive-ui'
import { useBrandingStore, type BrandingSettings, type BrandingAsset } from '../../../stores/branding'
import { parseApiError } from '../../../utils/parseApiError'

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

// ── Hero background slots (morning / day / evening) ──────────────────────────
type HeroBgKind = 'hero-bg-morning' | 'hero-bg-day' | 'hero-bg-evening'
const heroBgSlots: { kind: HeroBgKind; labelKey: string }[] = [
  { kind: 'hero-bg-morning', labelKey: 'admin.branding.heroBgMorning' },
  { kind: 'hero-bg-day', labelKey: 'admin.branding.heroBgDay' },
  { kind: 'hero-bg-evening', labelKey: 'admin.branding.heroBgEvening' },
]
const heroInputRefs = reactive<Record<HeroBgKind, HTMLInputElement | null>>({
  'hero-bg-morning': null,
  'hero-bg-day': null,
  'hero-bg-evening': null,
})
function setHeroInputRef(kind: HeroBgKind, el: HTMLInputElement | null) {
  heroInputRefs[kind] = el
}
const heroBgBusy = reactive<Record<HeroBgKind, boolean>>({
  'hero-bg-morning': false,
  'hero-bg-day': false,
  'hero-bg-evening': false,
})
const heroBgResetBusy = reactive<Record<HeroBgKind, boolean>>({
  'hero-bg-morning': false,
  'hero-bg-day': false,
  'hero-bg-evening': false,
})

// Час-границы живут в общей brandingForm и сохраняются кнопкой «Сохранить» в
// секции «Общие настройки» (единая точка сохранения, как было до редизайна).
async function onHeroBgFileChange(e: Event, kind: HeroBgKind) {
  await pickAndUpload(e, kind, { get value() { return heroBgBusy[kind] }, set value(v: boolean) { heroBgBusy[kind] = v } }, 'admin.branding.heroBgUploaded')
}
async function onHeroBgReset(kind: HeroBgKind) {
  await resetAsset(kind, { get value() { return heroBgResetBusy[kind] }, set value(v: boolean) { heroBgResetBusy[kind] = v } }, 'admin.branding.heroBgResetDone')
}

const brandingFormSaving = ref(false)
const brandingForm = ref<BrandingSettings>({ ...brandingStore.settings })

const bannerTypeOptions = computed(() => [
  { label: t('admin.branding.bannerTypeInfo'), value: 'info' },
  { label: t('admin.branding.bannerTypeWarning'), value: 'warning' },
  { label: t('admin.branding.bannerTypeError'), value: 'error' },
  { label: t('admin.branding.bannerTypeSuccess'), value: 'success' },
])

const heroSubtitleModeOptions = computed(() => [
  { label: t('admin.branding.heroSubtitleModeAuto'), value: 'auto' },
  { label: t('admin.branding.heroSubtitleModeCustom'), value: 'custom' },
  { label: t('admin.branding.heroSubtitleModeHidden'), value: 'hidden' },
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
  } catch (e) {
    message.error(parseApiError(e, t))
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
  } catch (e) {
    message.error(parseApiError(e, t))
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
  } catch (e) {
    message.error(parseApiError(e, t))
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

/* Hero background slots */
.hero-bg-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.hero-bg-tile {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hero-bg-tile__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}
.hero-bg-tile__preview {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
}
.hero-bg-tile__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.hero-bg-tile__placeholder {
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, var(--color-bg-muted), var(--color-border));
}
.hero-bg-tile__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
@media (max-width: 720px) {
  .hero-bg-grid { grid-template-columns: 1fr; }
}
</style>
