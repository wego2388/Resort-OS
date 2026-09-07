<script setup lang="ts">
// الشيكات (استلام/إيداع/تحصيل/ارتداد) — استُخرج من FinanceView.vue (تقسيم
// الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface Check { id: number; check_number: string; amount: number; drawer_name: string; due_date: string; status: string; bank_name: string }

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn } = useStaffFormat()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const checks = ref<Check[]>([])

const checkStatusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  received:  { label: t('backoffice.finance.checkReceived'),   variant: 'neutral' },
  deposited: { label: t('backoffice.finance.checkDeposited'),    variant: 'info' },
  cleared:   { label: t('backoffice.finance.checkCleared'),    variant: 'success' },
  bounced:   { label: t('backoffice.finance.checkBounced'),   variant: 'danger' },
}))

async function loadChecks() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.finance.checks, { params: { branch_id: branchId.value } })
    checks.value = res.data.checks ?? res.data.items ?? res.data
  } catch { toast.error(t('backoffice.finance.loadChecksError')) }
  finally { loading.value = false }
}

async function advanceCheck(check: Check) {
  const flow: Record<string, string> = { received: 'deposited', deposited: 'cleared' }
  const next = flow[check.status]
  if (!next) return
  try {
    await api.patch(ENDPOINTS.finance.checkStatus(check.id), { to_status: next })
    check.status = next
  } catch { toast.error(t('backoffice.finance.updateCheckStatusError')) }
}

// كانت الشاشة بتعرض بس مسار "إيداع → تحصيل" — مفيش أي زرار لتسجيل شيك
// مرتجع (bounced) رغم إن الحالة والـ endpoint موجودين بالكامل في الباك إند
// (راجع CHECK_STATUS_TRANSITIONS في finance/services.py). في الواقع نسبة لا
// يُستهان بها من الشيكات بترتد فعليًا (رصيد غير كافٍ) — فجوة UI صغيرة على
// ميزة موجودة، مش ميزة جديدة.
async function markCheckBounced(check: Check) {
  const ok = await confirm({
    message: t('backoffice.finance.confirmBounceMessage', { number: check.check_number, amount: formatNumber(check.amount) }),
    danger: true, confirmText: t('backoffice.finance.confirmBounceYes'), cancelText: t('backoffice.finance.confirmBounceNo'),
  })
  if (!ok) return
  try {
    await api.patch(ENDPOINTS.finance.checkStatus(check.id), {
      to_status: 'bounced', notes: t('backoffice.finance.bouncedNoteDefault'),
    })
    check.status = 'bounced'
    toast.success(t('backoffice.finance.checkMarkedBounced'))
  } catch { toast.error(t('backoffice.finance.updateCheckStatusError')) }
}

onMounted(loadChecks)
</script>

<template>
  <div>
    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[760px]">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.checkNumber') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.drawer') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.amount') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.dueDate') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.statusCol') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.action') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="check in checks" :key="check.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3 font-mono text-sm text-gray-900 dark:text-gray-100">{{ check.check_number }}</td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ check.drawer_name }}</td>
              <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(check.amount) }} {{ t('backoffice.finance.egp') }}</td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ fmtDateFn(check.due_date) }}</td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="checkStatusConfig[check.status]?.variant ?? 'neutral'">
                  {{ checkStatusConfig[check.status]?.label ?? check.status }}
                </AppBadge>
              </td>
              <td class="px-4 py-3">
                <div v-if="check.status === 'received' || check.status === 'deposited'" class="flex gap-2">
                  <AppButton size="sm" @click="advanceCheck(check)">
                    {{ check.status === 'received' ? t('backoffice.finance.deposit') : t('backoffice.finance.collect') }}
                  </AppButton>
                  <AppButton size="sm" variant="danger" @click="markCheckBounced(check)">
                    {{ t('backoffice.finance.bounced') }}
                  </AppButton>
                </div>
              </td>
            </tr>
            <tr v-if="checks.length === 0">
              <td colspan="6" class="px-4 py-8">
                <EmptyState icon="🏦" :title="t('backoffice.finance.noChecks')" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>
  </div>
</template>
