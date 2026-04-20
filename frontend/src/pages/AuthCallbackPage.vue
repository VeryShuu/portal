<template>
  <n-spin size="large" style="margin: 20vh auto; display: block" />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NSpin } from 'naive-ui'

const router = useRouter()

onMounted(() => {
  router.replace('/')
})
</script>
