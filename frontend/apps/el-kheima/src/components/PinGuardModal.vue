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
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { AppModal } from '@resort-os/ui'

const props = withDefaults(defineProps<{
  minLevel?: number
  title?: string
  message?: string
  loading?: boolean
  errorMessage?: string
}>(), {
  minLevel: 60,
  title: 'يتطلب موافقة مدير',
  message: '',
  loading: false,
  errorMessage: '',
})

const emit = defineEmits<{
  approved: [{ approverUserId: number | null; approverPin: string | null }]
  cancel: []
}>()

const auth = useAuthStore()
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
    localError.value = 'تعذّر تحميل قائمة المديرين'
  } finally {
    loadingApprovers.value = false
  }
})

function confirmApproval() {
  localError.value = ''
  if (!approverUserId.value || approverPin.value.length < 4) {
    localError.value = 'اختر المدير وأدخل رقم الـ PIN بتاعه'
    return
  }
  emit('approved', { approverUserId: approverUserId.value, approverPin: approverPin.value })
}
</script>

<template>
  <AppModal v-if="!selfQualified" :open="true" :title="title" size="sm" @close="emit('cancel')">
    <div class="space-y-2.5 min-w-[260px]" dir="rtl">
      <p v-if="message" class="text-xs text-gray-500">{{ message }}</p>
      <div v-if="loadingApprovers" class="text-center text-sm text-gray-400 py-3">جاري التحميل...</div>
      <template v-else-if="approvers.length === 0">
        <p class="text-center text-sm text-gray-400 py-3">مفيش مدير عنده PIN مضبوط حاليًا</p>
      </template>
      <template v-else>
        <select v-model="approverUserId" class="w-full border border-stone-300 rounded-lg p-2 text-sm">
          <option :value="null" disabled>اختر المدير...</option>
          <option v-for="a in approvers" :key="a.id" :value="a.id">{{ a.full_name }}</option>
        </select>
        <input
          v-model="approverPin"
          type="password"
          inputmode="numeric"
          maxlength="6"
          placeholder="PIN المدير"
          autofocus
          class="w-full border border-stone-300 rounded-lg p-2.5 text-center text-lg tracking-[0.4em] focus:outline-none focus:ring-2 focus:ring-amber-400"
          @keyup.enter="confirmApproval"
        />
      </template>
      <p v-if="localError || errorMessage" class="text-xs text-red-600">{{ localError || errorMessage }}</p>
    </div>
    <template #footer>
      <div class="flex gap-2">
        <button
          :disabled="loading"
          @click="emit('cancel')"
          class="flex-1 py-2 text-sm font-semibold text-gray-600 border border-stone-200 rounded-lg disabled:opacity-50"
        >إلغاء</button>
        <button
          :disabled="loading || loadingApprovers || approvers.length === 0"
          @click="confirmApproval"
          class="flex-1 py-2 text-sm font-bold text-white bg-amber-600 rounded-lg disabled:opacity-50"
        >{{ loading ? '...' : 'تأكيد الموافقة' }}</button>
      </div>
    </template>
  </AppModal>
</template>
