<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@resort-os/core'
import { AppButton } from '@resort-os/ui'
import { homeRouteFor } from '../../router/index'

const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

function goHome() {
  router.push(homeRouteFor(auth.role))
}

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    goHome()
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-stone-50 dark:bg-gray-950 px-4">
    <div class="w-full max-w-sm text-center">
      <div class="mb-4 text-7xl" role="img" aria-label="404">🧭</div>
      <h1 class="mb-2 text-3xl font-black text-gray-900 dark:text-gray-100">404</h1>
      <p class="mb-1 text-lg font-semibold text-gray-700 dark:text-gray-200">
        {{ t('notFound.title') }}
      </p>
      <p class="mb-8 text-sm text-gray-500 dark:text-gray-400">
        {{ t('notFound.subtitle') }}
      </p>
      <div class="flex flex-col gap-3 sm:flex-row sm:justify-center">
        <AppButton variant="outline" @click="goBack">
          ← {{ t('notFound.back') }}
        </AppButton>
        <AppButton variant="primary" @click="goHome">
          {{ t('notFound.home') }}
        </AppButton>
      </div>
    </div>
  </div>
</template>
