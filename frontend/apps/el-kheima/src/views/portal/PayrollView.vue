<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()

interface Payslip {
  id: number; period_year: number; period_month: number; status: string
  basic_salary: number; gross_salary: number; net_salary: number
  employee_si: number; monthly_tax: number
  penalty_deduction: number; unpaid_leave_deduction: number
}

const payslips = ref<Payslip[]>([])
const loading = ref(false)
const expanded = ref<number | null>(null)

const monthNames = ['', 'january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december']
function monthLabel(m: number) {
  return t(`backoffice.payroll.month.${monthNames[m]}`)
}

function totalDeductions(slip: Payslip) {
  return slip.employee_si + slip.monthly_tax + slip.penalty_deduction + slip.unpaid_leave_deduction
}
function totalAllowances(slip: Payslip) {
  return slip.gross_salary - slip.basic_salary
}

async function fetchPayslips() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.hr_extra.mePayslips)
    payslips.value = res.data.items ?? []
  } catch(e) {
    toast.error(t('backoffice.payroll.msg.loadError'))
  } finally { loading.value = false }
}

onMounted(fetchPayslips)
</script>

<template>
  <div class="space-y-4">
    <h2 class="font-bold text-gray-900 dark:text-gray-100 text-lg">{{ t('backoffice.payroll.title') }}</h2>

    <div v-if="loading" class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500 gap-3">
      <AppSpinner size="lg" />
      <p>{{ t('backoffice.payroll.loading') }}</p>
    </div>

    <div v-else class="space-y-3">
      <div v-for="slip in payslips" :key="slip.id"
        class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border shadow-sm overflow-hidden">
        <!-- Header (always visible) -->
        <button @click="expanded = expanded === slip.id ? null : slip.id"
          class="w-full px-5 py-4 flex items-center justify-between hover:bg-stone-50 dark:bg-gray-800/60 transition-colors">
          <div class="text-start">
            <div class="font-bold text-gray-900 dark:text-gray-100">
              {{ monthLabel(slip.period_month) }} {{ slip.period_year }}
            </div>
          </div>
          <div class="flex items-center gap-3">
            <div class="text-end">
              <div class="text-xl font-black text-blue-700">{{ formatNumber(Number(slip.net_salary)) }} <span class="text-sm font-normal">{{ t('backoffice.payroll.currency') }}</span></div>
              <span :class="['px-2 py-0.5 rounded-full text-xs font-medium block text-center', slip.status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700']">
                {{ slip.status === 'paid' ? t('backoffice.payroll.statusPaid') : t('backoffice.payroll.statusApproved') }}
              </span>
            </div>
            <svg :class="['w-4 h-4 text-gray-400 dark:text-gray-500 transition-transform', expanded === slip.id ? 'rotate-180' : '']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
            </svg>
          </div>
        </button>

        <!-- Details (expandable) -->
        <div v-if="expanded === slip.id" class="border-t border-stone-100 dark:border-border/50 px-5 py-4 space-y-2.5 bg-stone-50 dark:bg-gray-800/60">
          <div class="flex justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.payroll.basicSalary') }}</span>
            <span class="font-medium text-gray-900 dark:text-gray-100">{{ formatNumber(Number(slip.basic_salary)) }} {{ t('backoffice.payroll.currency') }}</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.payroll.allowances') }}</span>
            <span class="font-medium text-green-600">+ {{ formatNumber(Number(totalAllowances(slip))) }} {{ t('backoffice.payroll.currency') }}</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.payroll.socialInsurance') }}</span>
            <span class="font-medium text-red-500">- {{ formatNumber(Number(slip.employee_si)) }} {{ t('backoffice.payroll.currency') }}</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.payroll.monthlyTax') }}</span>
            <span class="font-medium text-red-500">- {{ formatNumber(Number(slip.monthly_tax)) }} {{ t('backoffice.payroll.currency') }}</span>
          </div>
          <div v-if="slip.penalty_deduction > 0" class="flex justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.payroll.penaltyDeduction') }}</span>
            <span class="font-medium text-red-500">- {{ formatNumber(Number(slip.penalty_deduction)) }} {{ t('backoffice.payroll.currency') }}</span>
          </div>
          <div v-if="slip.unpaid_leave_deduction > 0" class="flex justify-between text-sm">
            <span class="text-gray-500 dark:text-gray-500">{{ t('backoffice.payroll.unpaidLeaveDeduction') }}</span>
            <span class="font-medium text-red-500">- {{ formatNumber(Number(slip.unpaid_leave_deduction)) }} {{ t('backoffice.payroll.currency') }}</span>
          </div>
          <div class="flex justify-between text-base font-black pt-2 border-t border-stone-200 dark:border-border">
            <span class="text-gray-900 dark:text-gray-100">{{ t('backoffice.payroll.netSalary') }}</span>
            <span class="text-blue-700">{{ formatNumber(Number(slip.net_salary)) }} {{ t('backoffice.payroll.currency') }}</span>
          </div>
        </div>
      </div>

      <div v-if="payslips.length === 0" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border">
        <EmptyState icon="💰" :title="t('backoffice.payroll.noPayslips')" />
      </div>
    </div>
  </div>
</template>
