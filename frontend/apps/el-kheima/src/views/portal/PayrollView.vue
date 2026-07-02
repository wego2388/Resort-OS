<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'

const h = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }

interface Payslip {
  id: number; period_year: number; period_month: number; status: string
  basic_salary: number; gross_salary: number; net_salary: number
  employee_si: number; monthly_tax: number
  penalty_deduction: number; unpaid_leave_deduction: number
}

const payslips = ref<Payslip[]>([])
const loading = ref(false)
const expanded = ref<number | null>(null)

const monthNames = ['', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
  'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']

function totalDeductions(slip: Payslip) {
  return slip.employee_si + slip.monthly_tax + slip.penalty_deduction + slip.unpaid_leave_deduction
}
function totalAllowances(slip: Payslip) {
  return slip.gross_salary - slip.basic_salary
}

async function fetchPayslips() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/hr/me/payslips', { headers: h })
    payslips.value = res.data.items ?? []
  } catch(e) { console.error(e) }
  finally { loading.value = false }
}

onMounted(fetchPayslips)
</script>

<template>
  <div dir="rtl" class="space-y-4">
    <h2 class="font-bold text-gray-900 text-lg">قسائم الراتب</h2>

    <div v-if="loading" class="text-center py-12 text-gray-400">جاري التحميل...</div>

    <div v-else class="space-y-3">
      <div v-for="slip in payslips" :key="slip.id"
        class="bg-white rounded-2xl border border-stone-200 shadow-sm overflow-hidden">
        <!-- Header (always visible) -->
        <button @click="expanded = expanded === slip.id ? null : slip.id"
          class="w-full px-5 py-4 flex items-center justify-between hover:bg-stone-50 transition-colors">
          <div class="text-right">
            <div class="font-bold text-gray-900">
              {{ monthNames[slip.period_month] }} {{ slip.period_year }}
            </div>
          </div>
          <div class="flex items-center gap-3">
            <div class="text-left">
              <div class="text-xl font-black text-blue-700">{{ Number(slip.net_salary).toLocaleString('ar-EG') }} <span class="text-sm font-normal">ج</span></div>
              <span :class="['px-2 py-0.5 rounded-full text-xs font-medium block text-center', slip.status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700']">
                {{ slip.status === 'paid' ? 'مصروف' : 'معتمد' }}
              </span>
            </div>
            <svg :class="['w-4 h-4 text-gray-400 transition-transform', expanded === slip.id ? 'rotate-180' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
            </svg>
          </div>
        </button>

        <!-- Details (expandable) -->
        <div v-if="expanded === slip.id" class="border-t border-stone-100 px-5 py-4 space-y-2.5 bg-stone-50">
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">الراتب الأساسي</span>
            <span class="font-medium text-gray-900">{{ Number(slip.basic_salary).toLocaleString('ar-EG') }} ج</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">البدلات</span>
            <span class="font-medium text-green-600">+ {{ Number(totalAllowances(slip)).toLocaleString('ar-EG') }} ج</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">التأمينات الاجتماعية</span>
            <span class="font-medium text-red-500">- {{ Number(slip.employee_si).toLocaleString('ar-EG') }} ج</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">الضريبة الشهرية</span>
            <span class="font-medium text-red-500">- {{ Number(slip.monthly_tax).toLocaleString('ar-EG') }} ج</span>
          </div>
          <div v-if="slip.penalty_deduction > 0" class="flex justify-between text-sm">
            <span class="text-gray-500">خصم جزاءات</span>
            <span class="font-medium text-red-500">- {{ Number(slip.penalty_deduction).toLocaleString('ar-EG') }} ج</span>
          </div>
          <div v-if="slip.unpaid_leave_deduction > 0" class="flex justify-between text-sm">
            <span class="text-gray-500">خصم إجازة بدون راتب</span>
            <span class="font-medium text-red-500">- {{ Number(slip.unpaid_leave_deduction).toLocaleString('ar-EG') }} ج</span>
          </div>
          <div class="flex justify-between text-base font-black pt-2 border-t border-stone-200">
            <span class="text-gray-900">صافي الراتب</span>
            <span class="text-blue-700">{{ Number(slip.net_salary).toLocaleString('ar-EG') }} ج</span>
          </div>
        </div>
      </div>

      <div v-if="payslips.length === 0" class="text-center py-12 text-gray-400 bg-white rounded-2xl border border-stone-200">
        <div class="text-4xl mb-3">💰</div>
        <p class="font-medium text-gray-600">لا توجد قسائم راتب</p>
      </div>
    </div>
  </div>
</template>
