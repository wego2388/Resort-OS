<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore, type AllowedBranch } from '@resort-os/core'

const auth = useAuthStore()
const router = useRouter()
const { t, locale } = useI18n()
const switchingId = ref<number | null>(null)
const error = ref('')

function branchLabel(branch: AllowedBranch): string {
  return locale.value === 'ar' && branch.name_ar
    ? branch.name_ar
    : branch.name
}

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

// Auto-select: لو المستخدم عنده فرع واحد بالظبط ووصل هنا (كاشير/موظف جديد
// عمل login وكان branchId=null لأسباب تقنية)، نختار الفرع تلقائياً بدون ما
// نضيف خطوة إضافية غير ضرورية. لو في أكثر من فرع، نعرض الاختيار كالمعتاد.
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

      <div v-if="auth.branches.length" class="space-y-3">
        <button
          v-for="branch in auth.branches"
          :key="branch.id"
          type="button"
          :disabled="switchingId !== null"
          class="flex min-h-16 w-full items-center justify-between gap-3 rounded-2xl border border-stone-200 px-4 py-3 text-start transition hover:border-amber-500 hover:bg-amber-50 disabled:opacity-60 dark:border-gray-700 dark:hover:border-amber-500 dark:hover:bg-amber-950/20"
          @click="selectBranch(branch.id)"
        >
          <span>
            <strong class="block text-gray-900 dark:text-white">{{ branchLabel(branch) }}</strong>
            <span class="text-sm text-gray-500 dark:text-gray-400">{{ branch.code }} · {{ branch.timezone }}</span>
          </span>
          <span aria-hidden="true">{{ switchingId === branch.id ? '…' : '←' }}</span>
        </button>
      </div>

      <div v-else class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        {{ t('backoffice.layout.noAssignedBranches') }}
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
