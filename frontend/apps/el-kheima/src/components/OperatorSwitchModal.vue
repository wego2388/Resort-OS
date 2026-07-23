<script setup lang="ts">
/**
 * OperatorSwitchModal — تبديل هوية المشغّل على جهاز كاشير واحد بدون
 * logout/login كامل (راجع core.services.pin_switch_login بالباك إند).
 *
 * الفرق عن تسجيل الدخول العادي: الجهاز نفسه فضل "مسجّل دخوله" طول الوقت
 * (مدير أو أي حد فتح الشيفت الأول مرة)، والموظف بعد كده بس بيدوس اسمه
 * ويدخل الـ PIN بتاعه (4-6 أرقام) عشان كل عملية بعد كده (بيع، إلغاء...)
 * تتسجل باسمه هو فعليًا مش باسم أول حد سجّل دخول على الجهاز.
 *
 * Gate 5 i18n — النصوص متنقلة للـ backoffice.operatorSwitch namespace.
 * ROLE_LABEL متنقلة لـ backoffice.permissions.roles (موجودة أصلاً).
 */
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { AppModal, AppButton, useToast } from '@resort-os/ui'

const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore()
const toast = useToast()
const { t } = useI18n()

interface Operator { id: number; full_name: string; role: string }

const operators = ref<Operator[]>([])
const loading = ref(true)
const selectedId = ref<number | null>(null)
const pin = ref('')
const busy = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    // min_level=20 عشان تجيب كل الموظفين التشغيليين (مش المديرين بس زي
    // شاشة موافقة الـ PIN) — الباك إند برضه بيرفض أي هدف فوق مستوى مدير
    // (PIN_SWITCH_MAX_ROLE_LEVEL) بغض النظر عن اللي القائمة دي بترجعه.
    const { data } = await api.get(ENDPOINTS.core.pinApprovers, { params: { min_level: 20 } })
    operators.value = data.filter((o: Operator) => o.id !== auth.user?.id)
  } catch {
    error.value = t('backoffice.operatorSwitch.loadError')
  } finally {
    loading.value = false
  }
})

function selectOperator(id: number) {
  selectedId.value = id
  pin.value = ''
  error.value = ''
}

async function confirmSwitch() {
  if (!selectedId.value || pin.value.length < 4) {
    error.value = t('backoffice.operatorSwitch.error')
    return
  }
  busy.value = true
  error.value = ''
  try {
    await auth.pinSwitch(selectedId.value, pin.value)
    toast.success(t('backoffice.operatorSwitch.switchSuccess', { name: auth.user?.full_name }))
    emit('close')
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? t('backoffice.operatorSwitch.switchError')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal :open="true" :title="t('backoffice.operatorSwitch.title')" size="sm" @close="emit('close')">
    <div class="min-w-[280px] space-y-3">
      <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.operatorSwitch.hint') }}</p>

      <div v-if="loading" class="py-4 text-center text-sm text-gray-400 dark:text-gray-500">
        {{ t('backoffice.operatorSwitch.loading') }}
      </div>
      <div v-else-if="operators.length === 0" class="py-4 text-center text-sm text-gray-400 dark:text-gray-500">
        {{ t('backoffice.operatorSwitch.empty') }}
      </div>
      <div v-else class="grid grid-cols-2 gap-2">
        <button
          v-for="op in operators"
          :key="op.id"
          class="rounded-lg border p-2.5 text-start transition-colors"
          :class="selectedId === op.id
            ? 'border-blue-600 bg-blue-50 ring-2 ring-blue-200 dark:border-blue-500 dark:bg-blue-950/40 dark:ring-blue-800'
            : 'border-stone-200 hover:bg-gray-50 dark:border-border dark:hover:bg-gray-800'"
          @click="selectOperator(op.id)"
        >
          <div class="text-sm font-semibold text-gray-800 dark:text-gray-200">{{ op.full_name }}</div>
          <div class="text-xs text-gray-400 dark:text-gray-500">
            {{ t(`backoffice.permissions.roles.${op.role}`, op.role) }}
          </div>
        </button>
      </div>

      <input
        v-if="selectedId"
        v-model="pin"
        type="password"
        inputmode="numeric"
        maxlength="6"
        :placeholder="t('backoffice.operatorSwitch.pinPlaceholder')"
        autofocus
        class="w-full rounded-xl border border-stone-300 bg-white p-2.5 text-center text-lg tracking-[0.4em] text-gray-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-400/30 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
        @keyup.enter="confirmSwitch"
      />

      <p v-if="error" role="alert" class="text-xs text-red-600 dark:text-red-300">{{ error }}</p>
    </div>

    <template #footer>
      <div class="flex gap-2">
        <AppButton variant="outline" class="flex-1" :disabled="busy" @click="emit('close')">
          {{ t('backoffice.operatorSwitch.cancel') }}
        </AppButton>
        <AppButton
          variant="primary"
          class="flex-1"
          :loading="busy"
          :disabled="!selectedId || operators.length === 0"
          @click="confirmSwitch"
        >
          {{ busy ? t('backoffice.operatorSwitch.confirming') : t('backoffice.operatorSwitch.confirm') }}
        </AppButton>
      </div>
    </template>
  </AppModal>
</template>
