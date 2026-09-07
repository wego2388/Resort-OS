<script setup lang="ts">
// دليل الحسابات + كشف حساب (drill-down) — استُخرج من FinanceView.vue
// (تقسيم الملفات الكبيرة، 2026-09-07). accounts هنا نسخة محلية مستقلة
// (نفس نمط تكرار الجلب المتبع في باقي التابات المُستخرجة) — التابات
// التانية اللي لسه جوه FinanceView.vue (قنوات التحصيل/المصروفات/العهدة/
// إذن القبض/دفتر اليومية) لسها عندها نسخها الخاصة لقوائم الحسابات
// المنسدلة بتاعتها، ومفيش تزامن مباشر مطلوب.
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface AccountLedgerLineRow {
  entry_id: number; entry_date: string; reference: string; description: string
  debit: number; credit: number; running_balance: number
}
interface AccountLedgerData {
  account_id: number; account_code: string; account_name: string; account_type: string
  date_from: string; date_to: string
  opening_balance: number; closing_balance: number; total_debit: number; total_credit: number
  lines: AccountLedgerLineRow[]
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)

const loading = ref(false)
const accounts = ref<Account[]>([])

async function loadAccounts() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } })
    accounts.value = res.data.accounts ?? res.data.items ?? res.data
  } catch {
    toast.error(t('backoffice.finance.loadAccountsError'))
  } finally {
    loading.value = false
  }
}

// ── كشف حساب — drill-down لكل حساب (2026-08-19، طلب Mohamed) ──────────
const ledgerModal = reactive({ open: false, loading: false, error: '', account: null as Account | null, dateFrom: firstOfMonth, dateTo: today })
const ledgerData = ref<AccountLedgerData | null>(null)

async function loadAccountLedger() {
  if (!ledgerModal.account) return
  ledgerModal.loading = true
  ledgerModal.error = ''
  try {
    const { data } = await api.get(ENDPOINTS.finance.accountLedger(ledgerModal.account.id), {
      params: { branch_id: branchId.value, date_from: ledgerModal.dateFrom, date_to: ledgerModal.dateTo },
    })
    ledgerData.value = {
      ...data,
      opening_balance: Number(data.opening_balance),
      closing_balance: Number(data.closing_balance),
      total_debit: Number(data.total_debit),
      total_credit: Number(data.total_credit),
      lines: (data.lines ?? []).map((l: Record<string, unknown>) => ({
        ...l, debit: Number(l.debit), credit: Number(l.credit), running_balance: Number(l.running_balance),
      })),
    } as AccountLedgerData
  } catch (e: unknown) {
    ledgerModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.ledger.loadError')
  } finally {
    ledgerModal.loading = false
  }
}
function openAccountLedger(acc: Account) {
  ledgerModal.account = acc
  ledgerModal.open = true
  ledgerModal.dateFrom = firstOfMonth
  ledgerModal.dateTo = today
  ledgerData.value = null
  loadAccountLedger()
}
function closeAccountLedger() {
  ledgerModal.open = false
}

onMounted(loadAccounts)
</script>

<template>
  <div>
    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[600px]">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.code') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.accountName') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.type') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.balance') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="acc in accounts" :key="acc.id" class="cursor-pointer border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:hover:bg-gray-800/60" @click="openAccountLedger(acc)">
              <td class="px-4 py-3 font-mono text-sm text-gray-600 dark:text-gray-400">{{ acc.code }}</td>
              <td class="px-4 py-3 text-sm font-medium text-primary-700 dark:text-primary-300 underline decoration-dotted">{{ acc.name }}</td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ acc.account_type }}</td>
              <td class="px-4 py-3 text-sm font-bold" :class="acc.balance >= 0 ? 'text-green-600 dark:text-green-300' : 'text-red-500 dark:text-red-300'">
                {{ formatNumber(acc.balance) }} {{ t('backoffice.finance.egp') }}
              </td>
            </tr>
            <tr v-if="accounts.length === 0">
              <td colspan="4" class="px-4 py-8">
                <EmptyState icon="📒" :title="t('backoffice.finance.noAccounts')" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>

    <AppModal :open="ledgerModal.open" :title="ledgerModal.account ? `📒 ${ledgerModal.account.code} — ${ledgerModal.account.name}` : t('backoffice.finance.ledger.title')" size="lg" @close="closeAccountLedger">
      <div class="min-w-[280px]">
        <div class="flex flex-wrap items-end gap-3 mb-4">
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.fromDate') }}</label>
            <input v-model="ledgerModal.dateFrom" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.toDate') }}</label>
            <input v-model="ledgerModal.dateTo" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
          </div>
          <AppButton size="sm" :loading="ledgerModal.loading" @click="loadAccountLedger">{{ t('backoffice.finance.apply') }}</AppButton>
        </div>

        <div v-if="ledgerModal.loading" class="flex justify-center py-10"><AppSpinner size="lg" /></div>
        <p v-else-if="ledgerModal.error" class="text-sm text-red-600 dark:text-red-400">{{ ledgerModal.error }}</p>
        <template v-else-if="ledgerData">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-400 mb-1">{{ t('backoffice.finance.ledger.opening') }}</div>
              <div class="text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(ledgerData.opening_balance) }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-400 mb-1">{{ t('backoffice.finance.ledger.totalDebit') }}</div>
              <div class="text-sm font-bold text-green-600 dark:text-green-300">{{ formatNumber(ledgerData.total_debit) }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-400 mb-1">{{ t('backoffice.finance.ledger.totalCredit') }}</div>
              <div class="text-sm font-bold text-red-600 dark:text-red-300">{{ formatNumber(ledgerData.total_credit) }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-400 mb-1">{{ t('backoffice.finance.ledger.closing') }}</div>
              <div class="text-sm font-bold text-primary-700 dark:text-primary-300">{{ formatNumber(ledgerData.closing_balance) }}</div>
            </div>
          </div>
          <div class="overflow-x-auto max-h-[50vh] overflow-y-auto border border-stone-200 dark:border-border rounded-xl">
            <table class="w-full min-w-[600px]">
              <thead class="bg-stone-50 dark:bg-gray-800/60 sticky top-0">
                <tr>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.date') }}</th>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.reference') }}</th>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.description') }}</th>
                  <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.debit') }}</th>
                  <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.credit') }}</th>
                  <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.runningBalance') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="l in ledgerData.lines" :key="l.entry_id" class="border-t border-stone-100 dark:border-border/50">
                  <td class="px-3 py-2 text-xs text-gray-600 dark:text-gray-400">{{ fmtDateFn(l.entry_date) }}</td>
                  <td class="px-3 py-2 text-xs font-mono text-gray-600 dark:text-gray-400">{{ l.reference }}</td>
                  <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ l.description }}</td>
                  <td class="px-3 py-2 text-xs text-end font-semibold text-green-600 dark:text-green-300">{{ l.debit ? formatNumber(l.debit) : '—' }}</td>
                  <td class="px-3 py-2 text-xs text-end font-semibold text-red-600 dark:text-red-300">{{ l.credit ? formatNumber(l.credit) : '—' }}</td>
                  <td class="px-3 py-2 text-xs text-end font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.running_balance) }}</td>
                </tr>
                <tr v-if="ledgerData.lines.length === 0">
                  <td colspan="6" class="px-4 py-8"><EmptyState icon="📒" :title="t('backoffice.finance.noDataThisPeriod')" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
      <template #footer>
        <AppButton variant="ghost" class="w-full" @click="closeAccountLedger">{{ t('backoffice.finance.close') }}</AppButton>
      </template>
    </AppModal>
  </div>
</template>
