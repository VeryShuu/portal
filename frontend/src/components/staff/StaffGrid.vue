<template>
  <div
    class="staff-grid"
    :class="{ 'is-fetching': isFetching }"
  >
    <StaffCard
      v-for="u in users"
      :key="u.id"
      :user="u"
      :hl="hl"
      :attribute-schema="attributeSchema"
      :lang="lang"
    />
  </div>
</template>

<script setup lang="ts">
import StaffCard from './StaffCard.vue'
import type { UserPublic } from '../../api/users'
import type { UserAttributeMappingSchema } from '../../api/userAttributeMappings'

defineProps<{
  users: UserPublic[]
  hl: (text: string | null | undefined) => string
  attributeSchema: UserAttributeMappingSchema[]
  lang: 'ru' | 'en'
  isFetching: boolean
}>()
</script>

<style scoped>
.staff-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.staff-grid.is-fetching {
  opacity: 0.6;
  pointer-events: none;
  transition: opacity 0.15s ease;
}
@media print {
  .staff-grid { display: none !important; }
}
</style>
