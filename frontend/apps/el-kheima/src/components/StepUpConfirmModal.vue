<script setup lang="ts">
/**
 * StepUpConfirmModal — Gate 2B3A step-up control plane (frontend half).
 *
 * Confirms the *current signed-in user's own* identity (password + a fresh
 * TOTP code or one recovery code) right before a sensitive backend mutation
 * — NOT a PIN-based manager-approval gate (that's PinGuardModal.vue, a
 * completely different concept: "is a manager physically present and
 * approving", not "prove it's really you"). Do not merge these two ideas;
 * this component intentionally does not import or resemble PinGuardModal.
 *
 * Flow: the caller opens this modal with `purpose` + `intent` (the same
 * non-secret identifiers the protected endpoint will build its scope hash
 * from — see backend app/core/kernel/auth/step_up.py). On confirm, this
 * component alone calls POST /auth/step-up, then emits `confirmed` with a
 * one-time `stepUpToken` + the trimmed `reason` and immediately forgets
 * both from its own state. The caller is responsible for retrying its real
 * request with the `X-Step-Up-Token` header set to that token, exactly
 * once. If that retried request itself comes back with STEP_UP_INVALID
 * (expired/replayed/tampered proof), the caller should pass a fresh
 * `errorMessage` back in via props — this component then resets its
 * sensitive fields and asks the user to confirm again; it never resends
 * automatically.
 *
 * Security: current_password / totp_code / recovery_code / step_up_token
 * never touch localStorage or sessionStorage — they live only in this
 * component's local refs and are cleared the instant they've been used
 * (submitted, or handed off via the `confirmed` emit).
 *
 * Usage:
 *   <StepUpConfirmModal
 *     v-if="showStepUp" :purpose="'setting_upsert'"
 *     :intent="{ key: row.key, branch_id: branchId, value: newValue }"
 *     :description="t('backoffice.settings.reasonPromptSave', { key: row.key })"
 *     :loading="saving" :error-message="stepUpError"
 *     @confirmed="onStepUpConfirmed" @cancel="showStepUp = false"
 *   />
 */
import { nextTick, onMounted, ref, watch } from 'vue'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { AppModal, AppInput } from '@resort-os/ui'
import { useI18n } from 'vue-i18n'

const props = withDefaults(defineProps<{
  purpose: 'user_provision' | 'user_role_update' | 'permission_override_upsert' | 'permission_override_revoke' | 'setting_upsert' | 'session_revoke' | 'other_sessions_revoke' | 'payment_void' | 'dining_refund'
  intent: Record<string, unknown>
  description?: string
  loading?: boolean
  errorMessage?: string
  // Gate 2B3B: the session-revocation intents (session_revoke /
  // other_sessions_revoke) are `extra="forbid"` server-side and reject any
  // `reason` field. When false, the reason input is not rendered, its length
  // is not validated, and `reason` is NOT injected into the posted intent.
  // Defaults to true so every pre-existing caller is unchanged.
  requireReason?: boolean
}>(), {
  description: '',
  loading: false,
  errorMessage: '',
  requireReason: true,
})

const emit = defineEmits<{
  confirmed: [{ stepUpToken: string; reason: string }]
  cancel: []
}>()

const { t } = useI18n()
const auth = useAuthStore()
const needsTwoFactorCode = !!auth.user?.two_factor_enabled

const password = ref('')
const reason = ref('')
const totpCode = ref('')
const recoveryCode = ref('')
const useRecovery = ref(false)
const submitting = ref(false)
const localError = ref('')

// focus أول حقل تلقائيًا لما المودال يفتح — مراجعة Codex المستقلة
// (2026-07-18): مودال بلا focus management بيسيب لوحة المفاتيح على أي
// عنصر كان مفعّل قبل الفتح، مش على أول حقل فعلي جوه المودال نفسه.
const reasonInputRef = ref<InstanceType<typeof AppInput> | null>(null)
const passwordInputRef = ref<InstanceType<typeof AppInput> | null>(null)
onMounted(() => {
  // Focus the first real field inside the modal — the reason field when it's
  // rendered, otherwise the password field (Gate 2B3B: reasonless intents).
  nextTick(() => (props.requireReason ? reasonInputRef.value : passwordInputRef.value)?.focus())
})

function resetSensitiveFields() {
  password.value = ''
  totpCode.value = ''
  recoveryCode.value = ''
}

// Gate 2B3A: أي رفض STEP_UP_INVALID من الطلب الفعلي المُعاد (parent) بيبتدي
// دورة إثبات جديدة تمامًا — مفيش أي إعادة إرسال تلقائي، ومفيش أي حقل حسّاس
// قديم فاضل.
watch(() => props.errorMessage, (msg) => {
  if (msg) {
    resetSensitiveFields()
    localError.value = msg
  }
})

async function submit() {
  localError.value = ''
  const trimmedReason = reason.value.trim()
  if (props.requireReason && trimmedReason.length < 3) {
    localError.value = t('backoffice.stepUp.reasonRequired')
    return
  }
  if (needsTwoFactorCode) {
    if (useRecovery.value && !recoveryCode.value.trim()) {
      localError.value = t('backoffice.stepUp.errorCodeRequired')
      return
    }
    if (!useRecovery.value && !totpCode.value.trim()) {
      localError.value = t('backoffice.stepUp.errorCodeRequired')
      return
    }
  }

  submitting.value = true
  try {
    const payload: Record<string, unknown> = {
      current_password: password.value,
      purpose: props.purpose,
      // Gate 2B3B: reasonless intents must post EXACTLY `{ ...props.intent }` —
      // the backend intent models forbid an unexpected `reason` field.
      intent: props.requireReason ? { ...props.intent, reason: trimmedReason } : { ...props.intent },
    }
    if (needsTwoFactorCode) {
      if (useRecovery.value) payload.recovery_code = recoveryCode.value.trim()
      else payload.totp_code = totpCode.value.trim()
    }

    const res = await api.post(ENDPOINTS.auth.stepUp, payload)
    const stepUpToken: string = res.data.step_up_token

    // التوكن هيتسلّم للأب فورًا — مفيش داعي نحتفظ بأي حاجة حسّاسة هنا تاني.
    resetSensitiveFields()
    emit('confirmed', { stepUpToken, reason: props.requireReason ? trimmedReason : '' })
  } catch (e: any) {
    const code = e?.response?.data?.detail?.code
    if (code === 'CURRENT_PASSWORD_REQUIRED') localError.value = t('backoffice.stepUp.errorWrongPassword')
    else if (code === '2FA_CODE_REQUIRED') localError.value = t('backoffice.stepUp.errorCodeRequired')
    else if (code === '2FA_CODE_INVALID') localError.value = t('backoffice.stepUp.errorCodeInvalid')
    else if (code === 'MANDATORY_2FA_REQUIRED') localError.value = t('backoffice.stepUp.errorMandatory2FA')
    else localError.value = t('backoffice.stepUp.errorGeneric')
    // امسح الرمز بس (مش الباسورد ولا السبب) — تجربة أفضل لو الكود بس غلط
    totpCode.value = ''
    recoveryCode.value = ''
  } finally {
    submitting.value = false
  }
}

function cancel() {
  resetSensitiveFields()
  emit('cancel')
}
</script>

<template>
  <AppModal :open="true" :title="t('backoffice.stepUp.title')" size="sm" @close="cancel">
    <div class="space-y-3">
      <p v-if="description" class="text-sm text-gray-600 dark:text-gray-400">{{ description }}</p>

      <AppInput
        v-if="requireReason"
        ref="reasonInputRef"
        v-model="reason"
        :label="t('backoffice.stepUp.reasonLabel')"
        :placeholder="t('backoffice.stepUp.reasonPlaceholder')"
        :disabled="submitting || loading"
        autocomplete="off"
        required
      />

      <AppInput
        ref="passwordInputRef"
        v-model="password"
        type="password"
        :label="t('backoffice.stepUp.passwordLabel')"
        :placeholder="t('backoffice.stepUp.passwordPlaceholder')"
        :disabled="submitting || loading"
        autocomplete="current-password"
        required
      />

      <template v-if="needsTwoFactorCode">
        <AppInput
          v-if="!useRecovery"
          v-model="totpCode"
          :label="t('backoffice.stepUp.totpLabel')"
          :placeholder="t('backoffice.stepUp.totpPlaceholder')"
          :disabled="submitting || loading"
          autocomplete="one-time-code"
          inputmode="numeric"
          required
        />
        <AppInput
          v-else
          v-model="recoveryCode"
          :label="t('backoffice.stepUp.recoveryLabel')"
          :placeholder="t('backoffice.stepUp.recoveryPlaceholder')"
          :disabled="submitting || loading"
          autocomplete="off"
          required
        />
        <button
          type="button"
          class="text-xs font-semibold text-primary-700 dark:text-primary-400 hover:underline"
          :disabled="submitting || loading"
          @click="useRecovery = !useRecovery"
        >
          {{ useRecovery ? t('backoffice.stepUp.useTotpCode') : t('backoffice.stepUp.useRecoveryCode') }}
        </button>
      </template>

      <p v-if="localError" role="alert" aria-live="assertive" class="text-xs text-danger">{{ localError }}</p>
    </div>

    <template #footer>
      <div class="flex gap-2">
        <button
          :disabled="submitting || loading"
          @click="cancel"
          class="flex-1 py-2 text-sm font-semibold text-gray-600 dark:text-gray-300 border border-stone-200 dark:border-border rounded-lg disabled:opacity-50"
        >{{ t('backoffice.stepUp.cancelButton') }}</button>
        <button
          :disabled="submitting || loading"
          @click="submit"
          class="flex-1 py-2 text-sm font-bold text-white bg-primary-700 rounded-lg disabled:opacity-50"
        >{{ (submitting || loading) ? t('backoffice.stepUp.loading') : t('backoffice.stepUp.confirmButton') }}</button>
      </div>
    </template>
  </AppModal>
</template>
