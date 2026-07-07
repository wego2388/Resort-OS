<script setup lang="ts">
/**
 * OperatorSwitchModal — تبديل هوية المشغّل على جهاز كاشير واحد بدون
 * logout/login كامل (راجع core.services.pin_switch_login بالباك إند).
 *
 * الفرق عن تسجيل الدخول العادي: الجهاز نفسه فضل "مسجّل دخوله" طول الوقت
 * (مدير أو أي حد فتح الشيفت الأول مرة)، والموظف بعد كده بس بيدوس اسمه
 * ويدخل الـ PIN بتاعه (4-6 أرقام) عشان كل عملية بعد كده (بيع، إلغاء...)
 * تتسجل باسمه هو فعليًا مش باسم أول حد سجّل دخول على الجهاز.
 */
import { ref, onMounted } from 'vue'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { AppModal, useToast } from '@resort-os/ui'

const emit = defineEmits<{ close: [] }>()
const auth = useAuthStore()
const toast = useToast()

interface Operator { id: number; full_name: string; role: string }

const operators = ref<Operator[]>([])
const loading = ref(true)
const selectedId = ref<number | null>(null)
const pin = ref('')
const busy = ref(false)
const error = ref('')

const ROLE_LABEL: Record<string, string> = {
  manager: 'مدير', supervisor: 'مشرف', cashier: 'كاشير',
  receptionist: 'استقبال', waiter: 'نادل', chef: 'شيف',
  kitchen: 'مطبخ', employee: 'موظف',
}

onMounted(async () => {
  try {
    // min_level=20 عشان تجيب كل الموظفين التشغيليين (مش المديرين بس زي
    // شاشة موافقة الـ PIN) — الباك إند برضه بيرفض أي هدف فوق مستوى مدير
    // (PIN_SWITCH_MAX_ROLE_LEVEL) بغض النظر عن اللي القائمة دي بترجعه.
    const { data } = await api.get(ENDPOINTS.core.pinApprovers, { params: { min_level: 20 } })
    operators.value = data.filter((o: Operator) => o.id !== auth.user?.id)
  } catch {
    error.value = 'فشل تحميل قائمة الموظفين'
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
    error.value = 'اختر اسمك وأدخل الـ PIN بتاعك'
    return
  }
  busy.value = true
  error.value = ''
  try {
    await auth.pinSwitch(selectedId.value, pin.value)
    toast.success(`تم التبديل — أهلاً ${auth.user?.full_name} 👋`)
    emit('close')
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'فشل التبديل — تأكد من الـ PIN'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal :open="true" title="تبديل المشغّل" size="sm" @close="emit('close')">
    <div class="space-y-3 min-w-[280px]">
      <p class="text-xs text-gray-500">اختر اسمك وأدخل رقم الـ PIN بتاعك (4-6 أرقام)</p>

      <div v-if="loading" class="text-center text-sm text-gray-400 py-4">جاري التحميل...</div>
      <div v-else-if="operators.length === 0" class="text-center text-sm text-gray-400 py-4">
        مفيش موظفين تانيين عندهم PIN مضبوط
      </div>
      <div v-else class="grid grid-cols-2 gap-2">
        <button
          v-for="op in operators"
          :key="op.id"
          @click="selectOperator(op.id)"
          class="p-2.5 rounded-lg border text-right transition-colors"
          :class="selectedId === op.id
            ? 'border-blue-600 bg-blue-50 ring-2 ring-blue-200'
            : 'border-stone-200 hover:bg-gray-50'"
        >
          <div class="text-sm font-semibold text-gray-800">{{ op.full_name }}</div>
          <div class="text-xs text-gray-400">{{ ROLE_LABEL[op.role] ?? op.role }}</div>
        </button>
      </div>

      <input
        v-if="selectedId"
        v-model="pin"
        type="password"
        inputmode="numeric"
        maxlength="6"
        placeholder="PIN"
        autofocus
        class="w-full border border-stone-300 rounded-lg p-2.5 text-center text-lg tracking-[0.4em] focus:outline-none focus:ring-2 focus:ring-blue-400"
        @keyup.enter="confirmSwitch"
      />

      <p v-if="error" class="text-xs text-red-600">{{ error }}</p>

      <div class="flex gap-2 pt-1">
        <button @click="emit('close')" class="flex-1 py-2 text-sm font-semibold text-gray-600 border border-stone-200 rounded-lg">إلغاء</button>
        <button
          :disabled="busy || !selectedId"
          @click="confirmSwitch"
          class="flex-1 py-2 text-sm font-bold text-white bg-blue-700 rounded-lg disabled:opacity-50"
        >تأكيد</button>
      </div>
    </div>
  </AppModal>
</template>
