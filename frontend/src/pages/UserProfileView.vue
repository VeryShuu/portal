<template>
  <div
    class="profile-wrap"
    :class="{ 'profile-wrap--view': !isOwn }"
  >
    <n-spin
      v-if="loading"
      style="margin: 60px auto; display: block"
    />

    <template v-else-if="user">
      <ProfileHero
        :user="user"
        :is-own="isOwn"
      />

      <div
        class="profile-grid"
        :class="{ 'profile-grid--view': !isOwn }"
      >
        <ProfileInfoCard
          :user="user"
          :is-own="isOwn"
          :extra-attributes="extraAttributes"
        />

        <ProfileGroupsCard
          v-if="auth.isAdmin"
          :groups="groups"
          :loading="groupsLoading"
        />

        <ProfilePreferencesCard v-if="isOwn" />

        <ProfilePasswordCard v-if="isOwn && auth.isLocalUser" />

        <DepartmentColleagues
          v-if="user.department"
          :department="user.department"
          :exclude-user-id="user.id"
        />
      </div>
    </template>

    <div
      v-else
      class="profile-notfound"
    >
      <n-result
        status="404"
        :title="t('users.notFound')"
        :description="t('errors.notFound.description')"
      >
        <template #footer>
          <n-button @click="router.back()">
            {{ t('common.back') }}
          </n-button>
        </template>
      </n-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NSpin, NResult } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import type { UserPublic } from '../api/users'
import type { UserMe } from '../api/auth'
import DepartmentColleagues from '../components/profile/DepartmentColleagues.vue'
import ProfileHero from '../components/profile/ProfileHero.vue'
import ProfileInfoCard from '../components/profile/ProfileInfoCard.vue'
import ProfileGroupsCard from '../components/profile/ProfileGroupsCard.vue'
import ProfilePreferencesCard from '../components/profile/ProfilePreferencesCard.vue'
import ProfilePasswordCard from '../components/profile/ProfilePasswordCard.vue'
import { useUserQuery, useUserAttributeSchemaQuery, useUserKeycloakGroupsQuery } from '../queries/users'

type DisplayUser = UserMe | UserPublic

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const auth = useAuthStore()

const isOwn = computed(() => route.name === 'profile')
const viewedUserId = computed(() => route.params.id as string ?? '')

const { data: fetchedUser, isLoading: loading } = useUserQuery(viewedUserId, {
  enabled: computed(() => !isOwn.value && !!viewedUserId.value),
})

const { data: attrSchemaData } = useUserAttributeSchemaQuery()
const attrSchema = computed(() => attrSchemaData.value?.items ?? [])

const queriedGroupsUserId = computed(() =>
  isOwn.value ? (auth.user?.id ?? '') : viewedUserId.value,
)
const { data: groupsData, isLoading: groupsLoading } = useUserKeycloakGroupsQuery(
  queriedGroupsUserId,
  {
    enabled: computed(() =>
      auth.isAdmin && !!queriedGroupsUserId.value &&
      (isOwn.value ? !!auth.user : !!fetchedUser.value),
    ),
  },
)
const groups = computed(() => groupsData.value?.groups ?? [])

const user = computed<DisplayUser | null>(() =>
  isOwn.value ? auth.user : fetchedUser.value ?? null,
)

const extraAttributes = computed(() => {
  const attrs = fetchedUser.value?.attributes ?? {}
  const lang = fetchedUser.value?.lang ?? 'ru'
  const rows: Array<{ key: string; label: string; value: string }> = []
  for (const item of attrSchema.value) {
    const raw = attrs[item.attr_key]
    if (raw === undefined || raw === null || raw === '') continue
    const value = Array.isArray(raw) ? raw.filter(Boolean).join(', ') : String(raw)
    if (!value) continue
    const label = (lang === 'en' && item.label_en) ? item.label_en : item.label_ru
    rows.push({ key: item.attr_key, label, value })
  }
  return rows
})
</script>

<style scoped>
.profile-wrap {
  max-width: 1200px;
  margin: 0 auto;
}
.profile-wrap--view {
  max-width: 800px;
}

.profile-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.profile-grid--view {
  grid-template-columns: 1fr;
}

.profile-notfound {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

@media (max-width: 960px) {
  .profile-grid { grid-template-columns: 1fr; }
}
</style>
