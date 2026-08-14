<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@resort-os/core'

const auth = useAuthStore()
const router = useRouter()
const { t } = useI18n()
const switchingId = ref<number | null>(null)
const error = ref('')

async function selectBranch(branchId: number) {
  switchingId.value = branchId
  error.value = ''
  try {
    await auth.switchActiveBranch(branchId)
    await router.replace('/')
  } catch {
    error.value = t('backoffice.layout.branchSwitchFailed')
  } finally {
    switchingId.value = null
  }
}

async function logout() {
  await auth.logout()
}

// El Kheima is a single-branch operation. A single membership is selected
// automatically; zero or multiple memberships are a configuration error and
// deliberately never become a user-facing branch switcher.
onMounted(async () => {
  if (auth.branches.length === 1) {
    await selectBranch(auth.branches[0].id)
  }
})
</script>

<template>
  <main class="flex min-h-screen items-center justify-center bg-stone-100 p-4 dark:bg-gray-950">
    <section class="w-full max-w-xl rounded-3xl border border-stone-200 bg-white p-6 shadow-xl dark:border-gray-700 dark:bg-gray-900 sm:p-8">
      <div class="mb-6 text-center">
        <div class="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-600 text-2xl text-white">
          🏨
        </div>
        <h1 class="text-2xl font-black text-gray-900 dark:text-white">
          {{ t('backoffice.layout.chooseBranchTitle') }}
        </h1>
        <p class="mt-2 text-sm text-gray-600 dark:text-gray-300">
          {{ t('backoffice.layout.chooseBranchHint') }}
        </p>
      </div>

      <div v-if="auth.branches.length === 1" class="rounded-2xl border border-stone-200 bg-stone-50 p-4 text-center text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200" role="status">
        {{ t('backoffice.layout.settingOperatingBranch') }}
      </div>

      <div v-else-if="auth.branches.length === 0" class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        {{ t('backoffice.layout.noAssignedBranches') }}
      </div>

      <div v-else class="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200" role="alert">
        {{ t('backoffice.layout.multipleAssignedBranches') }}
      </div>

      <p v-if="error" class="mt-4 text-center text-sm text-red-600 dark:text-red-300" role="alert">
        {{ error }}
      </p>

      <button type="button" class="mt-6 w-full rounded-xl px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-950/30" @click="logout">
        {{ t('backoffice.layout.logout') }}
      </button>
    </section>
  </main>
</template>
