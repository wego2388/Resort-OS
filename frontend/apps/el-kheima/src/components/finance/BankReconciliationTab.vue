<script setup lang="ts">
// تسوية الحساب البنكي — استُخرج من FinanceView.vue (تقسيم الملفات الكبيرة،
// 2026-09-07). قائمة الحسابات البنكية هنا نسخة محلية مستقلة (نفس نمط
// تكرار الجلب المتبع في باقي التابات المُستخرجة) — تاب "قنوات التحصيل"
// المتبقي جوه FinanceView.vue لسه عنده نسخته الخاصة لاختيار الحساب
// البنكي في نموذج القناة، ومفيش تزامن مباشر مطلوب بين التابين.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface BankAccount {
  id: number; bank_name: string; account_name: string; account_number: string
  currency: string; opening_balance: number; is_active: boolean
}
interface StatementLine {
  id: number; line_date: string; description: string; amount: number
  status: string; external_reference?: string | null
}
interface ReconciliationSummary {
  opening_balance: number; book_balance: number; statement_balance: number
  difference: number; is_reconciled: boolean
  unmatched_statement_lines: number; unmatched_payments_count: number
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const bankAccounts = ref<BankAccount[]>([])
const selectedBankAccountId = ref<number | null>(null)
const statementLines = ref<StatementLine[]>([])
const reconciliationSummary = ref<ReconciliationSummary | null>(null)
const showBankAccountForm = ref(false)
const bankAccountForm = ref({ bank_name: '', account_name: '', account_number: '', opening_balance: '0' })
const matchingInProgress = ref(false)

async function loadBankAccounts() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.bankAccounts, { params: { branch_id: branchId.value } })
    bankAccounts.value = data
    if (!selectedBankAccountId.value && data.length) {
      selectedBankAccountId.value = data[0].id
      await loadStatementLinesAndSummary()
    }
  } catch { toast.error(t('backoffice.finance.loadBankAccountsError')) }
  finally { loading.value = false }
}

async function loadStatementLinesAndSummary() {
  if (!selectedBankAccountId.value) return
  try {
    const [linesRes, summaryRes] = await Promise.all([
      api.get(ENDPOINTS.finance.bankAccountStatementLines(selectedBankAccountId.value), {
        params: { size: 100 },
      }),
      api.get(ENDPOINTS.finance.bankAccountReconciliationSummary(selectedBankAccountId.value), {
        params: { as_of: new Date().toISOString().slice(0, 10) },
      }),
    ])
    statementLines.value = linesRes.data.items ?? []
    reconciliationSummary.value = summaryRes.data
  } catch { toast.error(t('backoffice.finance.loadReconciliationError')) }
}

async function createBankAccount() {
  if (!bankAccountForm.value.bank_name || !bankAccountForm.value.account_number) {
    toast.error(t('backoffice.finance.bankAccountFieldsRequired')); return
  }
  try {
    await api.post(ENDPOINTS.finance.bankAccounts, {
      branch_id: branchId.value,
      bank_name: bankAccountForm.value.bank_name,
      account_name: bankAccountForm.value.account_name || bankAccountForm.value.bank_name,
      account_number: bankAccountForm.value.account_number,
      opening_balance: bankAccountForm.value.opening_balance,
    })
    toast.success(t('backoffice.finance.bankAccountCreated'))
    showBankAccountForm.value = false
    bankAccountForm.value = { bank_name: '', account_name: '', account_number: '', opening_balance: '0' }
    await loadBankAccounts()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.bankAccountCreateError'))
  }
}

async function runAutoMatch() {
  if (!selectedBankAccountId.value) return
  matchingInProgress.value = true
  try {
    const { data } = await api.post(
      ENDPOINTS.finance.bankAccountAutoMatch(selectedBankAccountId.value),
    )
    toast.success(t('backoffice.finance.autoMatchedToast', { count: data.matched_count }))
    await loadStatementLinesAndSummary()
  } catch { toast.error(t('backoffice.finance.autoMatchError')) }
  finally { matchingInProgress.value = false }
}

const statementLineStatusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  unmatched: { label: t('backoffice.finance.stmtUnmatched'), variant: 'warning' },
  matched:   { label: t('backoffice.finance.stmtMatched'),     variant: 'success' },
  ignored:   { label: t('backoffice.finance.stmtIgnored'),    variant: 'neutral' },
}))

onMounted(loadBankAccounts)
</script>

<template>
  <div>
    <div class="flex justify-between items-center mb-4">
      <select v-if="bankAccounts.length" v-model.number="selectedBankAccountId" @change="loadStatementLinesAndSummary"
        class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm">
        <option v-for="ba in bankAccounts" :key="ba.id" :value="ba.id">
          {{ ba.bank_name }} — {{ ba.account_number }}
        </option>
      </select>
      <span v-else />
      <AppButton size="sm" @click="showBankAccountForm = !showBankAccountForm">
        {{ showBankAccountForm ? t('backoffice.finance.cancel') : t('backoffice.finance.newBankAccount') }}
      </AppButton>
    </div>

    <AppCard v-if="showBankAccountForm" class="mb-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input v-model="bankAccountForm.bank_name" type="text" :placeholder="t('backoffice.finance.bankName')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="bankAccountForm.account_name" type="text" :placeholder="t('backoffice.finance.accountNameOptional')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="bankAccountForm.account_number" type="text" :placeholder="t('backoffice.finance.accountNumber')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="bankAccountForm.opening_balance" type="number" step="0.01" :placeholder="t('backoffice.finance.openingBalance')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
      </div>
      <AppButton class="mt-3" size="sm" @click="createBankAccount">{{ t('backoffice.finance.saveAccount') }}</AppButton>
    </AppCard>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <EmptyState v-else-if="bankAccounts.length === 0" icon="🏦" :title="t('backoffice.finance.noBankAccountsYet')" />
    <template v-else>
      <div v-if="reconciliationSummary" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <AppCard padding="md" class="text-center">
          <div class="text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.bookBalance') }}</div>
          <div class="text-lg font-black text-gray-900 dark:text-gray-100">{{ formatNumber(reconciliationSummary.book_balance) }}</div>
        </AppCard>
        <AppCard padding="md" class="text-center">
          <div class="text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.statementBalance') }}</div>
          <div class="text-lg font-black text-gray-900 dark:text-gray-100">{{ formatNumber(reconciliationSummary.statement_balance) }}</div>
        </AppCard>
        <AppCard padding="md" class="text-center">
          <div class="text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.difference') }}</div>
          <div :class="['text-lg font-black', reconciliationSummary.is_reconciled ? 'text-green-600 dark:text-green-300' : 'text-amber-600 dark:text-amber-300']">
            {{ formatNumber(reconciliationSummary.difference) }}
          </div>
        </AppCard>
        <AppCard padding="md" class="text-center">
          <div class="text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.statusLabel') }}</div>
          <AppBadge :variant="reconciliationSummary.is_reconciled ? 'success' : 'warning'">
            {{ reconciliationSummary.is_reconciled ? `${t('backoffice.finance.reconciled')} ✓` : t('backoffice.finance.notReconciled') }}
          </AppBadge>
        </AppCard>
      </div>

      <div class="flex justify-end mb-3">
        <AppButton size="sm" :loading="matchingInProgress" @click="runAutoMatch">
          {{ t('backoffice.finance.autoMatchConservative') }}
        </AppButton>
      </div>

      <AppCard padding="none">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[600px]">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.date') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.description') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.amount') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.statusCol') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in statementLines" :key="line.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ line.line_date }}</td>
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">{{ line.description }}</td>
                <td class="px-4 py-3 text-sm font-bold" :class="line.amount >= 0 ? 'text-green-600 dark:text-green-300' : 'text-red-500 dark:text-red-300'">
                  {{ formatNumber(Number(line.amount)) }}
                </td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="statementLineStatusConfig[line.status]?.variant ?? 'neutral'">
                    {{ statementLineStatusConfig[line.status]?.label ?? line.status }}
                  </AppBadge>
                </td>
              </tr>
              <tr v-if="statementLines.length === 0">
                <td colspan="4" class="px-4 py-8">
                  <EmptyState icon="📄" :title="t('backoffice.finance.noStatementLines')" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </template>
  </div>
</template>
