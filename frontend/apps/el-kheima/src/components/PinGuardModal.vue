<script setup lang="ts">
/**
 * PinGuardModal — reusable PIN-approval gate for sensitive actions.
 *
 * Extracted (wagdy.md بند S-03) from the PIN-approval UI that used to live
 * only inline inside OrderDetailModal.vue (item void). Mirrors backend
 * core.services.resolve_pin_approval exactly:
 *   - if the current user's role level already clears `minLevel`, no PIN is
 *     required at all — the component renders nothing and emits `approved`
 *     immediately on mount with null approver fields (self-qualified).
 *   - otherwise it shows an approver picker + PIN input, and emits
 *     `approved` with the chosen { approverUserId, approverPin } once the
 *     user confirms. The component itself never validates the PIN — that
 *     only ever happens server-side, inside the real gated request the
 *     caller makes with these values (matches §4 CLAUDE.md: no business
 *     logic in the frontend).
 *
 * Controlled component: the parent decides when to mount it (v-if) and when
 * to unmount it (on success). Pass `:loading`/`:error-message` while the
 * real gated request is in flight so the user can see the outcome and, on
 * failure (e.g. wrong PIN), retry without losing their approver selection.
 *
 * Usage:
 *   <PinGuardModal
 *     v-if="showGuard" :min-level="60" title="يتطلب موافقة مدير"
 *     :loading="busy" :error-message="guardError"
 *     @approved="onApproved" @cancel="showGuard = false"
 *   />
 */
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { AppButton, AppModal } from '@resort-os/ui'

const props = withDefaults(defineProps<{
  minLevel?: number
  title?: string
  message?: string
  loading?: boolean
  errorMessage?: string
}>(), {
  minLevel: 60,
  title: '',
  message: '',
  loading: false,
  errorMessage: '',
})

const emit = defineEmits<{
  approved: [{ approverUserId: number | null; approverPin: string | null }]
  cancel: []
}>()

const auth = useAuthStore()
const { t } = useI18n()
// نفس شرط core.services.resolve_pin_approval بالظبط — لو مستوى المستخدم
// الحالي >= minLevel، مفيش داعي لموافقة PIN منفصلة، ومفيش أي UI يتعرض خالص.
const selfQualified = auth.roleLevel >= props.minLevel

interface Approver { id: number; full_name: string; role: string }
const approvers = ref<Approver[]>([])
const loadingApprovers = ref(false)
const approverUserId = ref<number | null>(null)
const approverPin = ref('')
const localError = ref('')

onMounted(async () => {
  if (selfQualified) {
    emit('approved', { approverUserId: null, approverPin: null })
    return
  }
  loadingApprovers.value = true
  try {
    const { data } = await api.get(ENDPOINTS.core.pinApprovers, { params: { min_level: props.minLevel } })
    approvers.value = data
  } catch {
    localError.value = t('backoffice.pinGuard.loadFailed')
  } finally {
    loadingApprovers.value = false
  }
})

function confirmApproval() {
  localError.value = ''
  if (!approverUserId.value || approverPin.value.length < 4) {
    localError.value = t('backoffice.pinGuard.validation')
    return
  }
  emit('approved', { approverUserId: approverUserId.value, approverPin: approverPin.value })
}
</script>

<template>
  <AppModal v-if="!selfQualified" :open="true" :title="title || t('backoffice.pinGuard.title')" size="sm" @close="emit('cancel')">
    <div class="min-w-[260px] space-y-3">
      <p v-if="message" class="text-sm text-gray-600 dark:text-gray-300">{{ message }}</p>
      <div v-if="loadingApprovers" class="py-3 text-center text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.pinGuard.loading') }}</div>
      <template v-else-if="approvers.length === 0">
        <p class="py-3 text-center text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.pinGuard.empty') }}</p>
      </template>
      <template v-else>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200" for="pin-approver">{{ t('backoffice.pinGuard.approver') }}</label>
        <select id="pin-approver" v-model="approverUserId" class="min-h-11 w-full rounded-xl border border-stone-300 bg-white px-3 text-sm text-gray-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-400/30 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100">
          <option :value="null" disabled>{{ t('backoffice.pinGuard.selectApprover') }}</option>
          <option v-for="a in approvers" :key="a.id" :value="a.id">{{ a.full_name }}</option>
        </select>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200" for="pin-code">{{ t('backoffice.pinGuard.pin') }}</label>
        <input
          id="pin-code"
          v-model="approverPin"
          type="password"
          inputmode="numeric"
          maxlength="6"
          :placeholder="t('backoffice.pinGuard.pinPlaceholder')"
          autofocus
          class="min-h-12 w-full rounded-xl border border-stone-300 bg-white p-2.5 text-center text-lg tracking-[0.4em] text-gray-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-400/30 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          @keyup.enter="confirmApproval"
        />
      </template>
      <p v-if="localError || errorMessage" role="alert" class="text-sm text-red-600 dark:text-red-300">{{ localError || errorMessage }}</p>
    </div>
    <template #footer>
      <div class="flex gap-2">
        <AppButton
          :disabled="loading"
          @click="emit('cancel')"
          variant="outline"
          class="flex-1"
        >{{ t('backoffice.pinGuard.cancel') }}</AppButton>
        <AppButton
          :disabled="loading || loadingApprovers || approvers.length === 0"
          @click="confirmApproval"
          variant="primary"
          class="flex-1"
        >{{ loading ? t('backoffice.pinGuard.approving') : t('backoffice.pinGuard.confirm') }}</AppButton>
      </div>
    </template>
  </AppModal>
</template>
