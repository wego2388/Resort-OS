<script setup lang="ts">
// دفتر اليومية + قيد يدوي جديد — استُخرج من FinanceView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07). accounts هنا نسخة محلية مستقلة (نفس نمط تكرار
// الجلب المتبع في باقي التابات المُستخرجة) عشان قائمة الحسابات المنسدلة
// في مودال القيد اليدوي.
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface JournalLine { account_id: number; account_code: string; account_name: string; debit: number; credit: number; description: string | null }
interface JournalEntry {
  id: number; entry_date: string; reference: string; description: string
  status: string; source: string | null; created_by: number; currency: string
  lines: JournalLine[]
}
interface NewJournalLine { accountId: number | null; debit: string; credit: string; description: string }

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)

const accounts = ref<Account[]>([])
const allAccountOptions = computed(() => accounts.value)

const journalEntries   = ref<JournalEntry[]>([])
const journalTotal     = ref(0)
const journalPage      = ref(1)
const journalDateFrom  = ref(firstOfMonth)
const journalDateTo    = ref(today)
const journalSource    = ref('')
const journalLoading   = ref(false)
const journalExpanded  = ref<number | null>(null)

async function loadAccounts() {
  if (accounts.value.length) return
  try {
    const res = await api.get(ENDPOINTS.finance.accounts, { params: { branch_id: branchId.value } })
    accounts.value = res.data.accounts ?? res.data.items ?? res.data
  } catch { /* لو فشل، مودال القيد اليدوي هيعرض قائمة فاضية بس مش هيمنع عرض الجدول */ }
}

async function loadJournal() {
  journalLoading.value = true
  try {
    const params: Record<string, unknown> = {
      branch_id: branchId.value,
      date_from: journalDateFrom.value,
      date_to:   journalDateTo.value,
      page: journalPage.value,
      size: 30,
    }
    if (journalSource.value) params.source = journalSource.value
    const { data } = await api.get(ENDPOINTS.finance.journalEntries, { params })
    journalEntries.value = (data.items ?? []).map((e: Record<string, unknown>) => ({
      ...e,
      lines: (e.lines as JournalLine[] ?? []).map((l: JournalLine) => ({
        ...l,
        debit:  Number(l.debit  ?? 0),
        credit: Number(l.credit ?? 0),
      })),
    }))
    journalTotal.value = data.total ?? 0
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.journal.loadError'))
  } finally {
    journalLoading.value = false
  }
}

const SOURCE_LABEL: Record<string, string> = {
  beach:      '🏖️ شاطئ',
  dining:     '🍽️ مطاعم',
  folio:      '🛎️ فوليو',
  payroll:    '💳 رواتب',
  inventory:  '📦 مخزون',
  depreciation: '📉 إهلاك',
  manual:     '✍️ يدوي',
}
function journalSourceLabel(src: string | null): string {
  if (!src) return '—'
  return SOURCE_LABEL[src] ?? src
}
function journalStatusVariant(s: string): 'success' | 'warning' | 'neutral' {
  if (s === 'posted') return 'success'
  if (s === 'draft')  return 'warning'
  return 'neutral'
}
function toggleJournalEntry(id: number) {
  journalExpanded.value = journalExpanded.value === id ? null : id
}

// ── قيد يدوي جديد (2026-08-16) ──────────────────────────────────────────
// POST /finance/journal-entries كان جاهزًا بالكامل في الباك إند (يتحقق من
// توازن مدين=دائن وقفل الفترة المحاسبية) بس مفيش أي شاشة كانت تستخدمه —
// المحاسب معندوش أي طريقة يسجّل بيها تسوية/تصحيح/سند دين أو ائتمان يدوي.
const newJournalModal = reactive({
  open: false, saving: false, error: '',
  entryDate: today, reference: '', description: '',
  lines: [
    { accountId: null, debit: '', credit: '', description: '' },
    { accountId: null, debit: '', credit: '', description: '' },
  ] as NewJournalLine[],
})
function openNewJournalModal() {
  loadAccounts()
  Object.assign(newJournalModal, {
    open: true, saving: false, error: '',
    entryDate: today, reference: '', description: '',
    lines: [
      { accountId: null, debit: '', credit: '', description: '' },
      { accountId: null, debit: '', credit: '', description: '' },
    ],
  })
}
function addJournalLine() {
  newJournalModal.lines.push({ accountId: null, debit: '', credit: '', description: '' })
}
function removeJournalLine(index: number) {
  if (newJournalModal.lines.length <= 2) return
  newJournalModal.lines.splice(index, 1)
}
const newJournalTotalDebit = computed(() =>
  newJournalModal.lines.reduce((sum, l) => sum + (Number(l.debit) || 0), 0))
const newJournalTotalCredit = computed(() =>
  newJournalModal.lines.reduce((sum, l) => sum + (Number(l.credit) || 0), 0))
const newJournalIsBalanced = computed(() =>
  Math.abs(newJournalTotalDebit.value - newJournalTotalCredit.value) < 0.01 && newJournalTotalDebit.value > 0)
async function confirmNewJournalEntry() {
  if (!newJournalModal.reference.trim() || !newJournalModal.description.trim()) {
    newJournalModal.error = t('backoffice.finance.journal.newEntry.validationError')
    return
  }
  if (newJournalModal.lines.some(l => !l.accountId || (!Number(l.debit) && !Number(l.credit)))) {
    newJournalModal.error = t('backoffice.finance.journal.newEntry.lineValidationError')
    return
  }
  if (!newJournalIsBalanced.value) {
    newJournalModal.error = t('backoffice.finance.journal.newEntry.unbalancedError')
    return
  }
  newJournalModal.saving = true
  newJournalModal.error = ''
  try {
    await api.post(ENDPOINTS.finance.journalEntries, {
      branch_id: branchId.value,
      entry_date: newJournalModal.entryDate,
      reference: newJournalModal.reference.trim(),
      description: newJournalModal.description.trim(),
      source: 'manual',
      lines: newJournalModal.lines.map(l => ({
        account_id: l.accountId,
        debit: Number(l.debit) || 0,
        credit: Number(l.credit) || 0,
        description: l.description.trim() || undefined,
      })),
    })
    toast.success(t('backoffice.finance.journal.newEntry.success'))
    newJournalModal.open = false
    journalPage.value = 1
    await loadJournal()
  } catch (e: unknown) {
    newJournalModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.journal.newEntry.error')
  } finally {
    newJournalModal.saving = false
  }
}

onMounted(loadJournal)
</script>

<template>
  <div class="space-y-4">
    <!-- فلاتر -->
    <AppCard padding="md">
      <div class="flex flex-wrap gap-3 items-end">
        <div>
          <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.dateFrom') }}</label>
          <input v-model="journalDateFrom" type="date"
            class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.dateTo') }}</label>
          <input v-model="journalDateTo" type="date"
            class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm" />
        </div>
        <div>
          <label class="block text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.finance.journal.source') }}</label>
          <select v-model="journalSource"
            class="rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-3 py-2 text-sm">
            <option value="">{{ t('backoffice.finance.all') }}</option>
            <option v-for="(label, src) in SOURCE_LABEL" :key="src" :value="src">{{ label }}</option>
          </select>
        </div>
        <AppButton variant="primary" :loading="journalLoading" @click="() => { journalPage = 1; loadJournal() }">
          {{ t('backoffice.finance.refresh') }}
        </AppButton>
        <AppButton variant="outline" class="ms-auto" @click="openNewJournalModal">
          ✍️ {{ t('backoffice.finance.journal.newEntry.btnLabel') }}
        </AppButton>
      </div>
    </AppCard>

    <!-- جدول القيود -->
    <AppCard padding="none">
      <div v-if="journalLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <EmptyState v-else-if="!journalEntries.length" icon="📒"
        :title="t('backoffice.finance.journal.empty')"
        :description="t('backoffice.finance.journal.emptyHint')" />
      <div v-else>
        <div class="px-4 py-2 border-b border-stone-100 dark:border-border/50 text-xs text-gray-500 dark:text-gray-400">
          {{ t('backoffice.finance.journal.totalEntries', { count: journalTotal }) }}
        </div>
        <div v-for="entry in journalEntries" :key="entry.id"
          class="border-b border-stone-100 dark:border-border/50 last:border-0">
          <!-- رأس القيد — قابل للطي -->
          <button
            class="w-full flex items-center gap-3 px-4 py-3 text-start hover:bg-stone-50 dark:hover:bg-gray-800/40 transition-colors"
            @click="toggleJournalEntry(entry.id)">
            <span class="text-gray-400 text-xs w-4 flex-shrink-0">{{ journalExpanded === entry.id ? '▼' : '▶' }}</span>
            <span class="text-xs text-gray-400 w-24 flex-shrink-0 tabular-nums">{{ entry.entry_date }}</span>
            <span class="font-mono text-xs text-gray-500 dark:text-gray-400 w-28 flex-shrink-0">{{ entry.reference }}</span>
            <span class="flex-1 text-sm text-gray-800 dark:text-gray-200 truncate">{{ entry.description }}</span>
            <span class="text-xs px-2">{{ journalSourceLabel(entry.source) }}</span>
            <AppBadge :variant="journalStatusVariant(entry.status)" size="sm">
              {{ entry.status === 'posted' ? t('backoffice.finance.journal.posted') : t('backoffice.finance.journal.draft') }}
            </AppBadge>
          </button>
          <!-- سطور القيد -->
          <div v-if="journalExpanded === entry.id" class="bg-stone-50 dark:bg-gray-800/30 border-t border-stone-100 dark:border-border/30">
            <table class="w-full text-xs">
              <thead>
                <tr class="text-gray-500 dark:text-gray-400">
                  <th class="px-6 py-2 text-start font-semibold">{{ t('backoffice.finance.journal.account') }}</th>
                  <th class="px-4 py-2 text-start font-semibold">{{ t('backoffice.finance.journal.description') }}</th>
                  <th class="px-4 py-2 text-end font-semibold">{{ t('backoffice.finance.journal.debit') }}</th>
                  <th class="px-4 py-2 text-end font-semibold">{{ t('backoffice.finance.journal.credit') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in entry.lines" :key="line.account_id"
                  class="border-t border-stone-100 dark:border-border/20">
                  <td class="px-6 py-1.5 font-mono">
                    <span class="text-gray-500 dark:text-gray-400">{{ line.account_code }}</span>
                    <span class="mx-1 text-gray-300">|</span>
                    <span class="text-gray-800 dark:text-gray-200">{{ line.account_name }}</span>
                  </td>
                  <td class="px-4 py-1.5 text-gray-500 dark:text-gray-400">{{ line.description ?? '—' }}</td>
                  <td class="px-4 py-1.5 text-end tabular-nums" :class="line.debit > 0 ? 'font-bold text-gray-900 dark:text-gray-100' : 'text-gray-300 dark:text-gray-600'">
                    {{ line.debit > 0 ? formatNumber(line.debit) : '—' }}
                  </td>
                  <td class="px-4 py-1.5 text-end tabular-nums" :class="line.credit > 0 ? 'font-bold text-gray-900 dark:text-gray-100' : 'text-gray-300 dark:text-gray-600'">
                    {{ line.credit > 0 ? formatNumber(line.credit) : '—' }}
                  </td>
                </tr>
                <!-- إجمالي القيد -->
                <tr class="border-t-2 border-stone-200 dark:border-border/50 bg-white dark:bg-gray-800/20 font-bold">
                  <td colspan="2" class="px-6 py-1.5 text-gray-500 dark:text-gray-400">{{ t('backoffice.finance.journal.total') }}</td>
                  <td class="px-4 py-1.5 text-end tabular-nums text-gray-900 dark:text-gray-100">
                    {{ formatNumber(entry.lines.reduce((s, l) => s + l.debit, 0)) }}
                  </td>
                  <td class="px-4 py-1.5 text-end tabular-nums text-gray-900 dark:text-gray-100">
                    {{ formatNumber(entry.lines.reduce((s, l) => s + l.credit, 0)) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <!-- Pagination -->
        <div v-if="journalTotal > 30" class="flex items-center justify-between px-4 py-3 border-t border-stone-100 dark:border-border/50">
          <span class="text-xs text-gray-500 dark:text-gray-400">
            {{ t('backoffice.finance.journal.page', { page: journalPage, total: Math.ceil(journalTotal / 30) }) }}
          </span>
          <div class="flex gap-2">
            <AppButton variant="outline" size="sm" :disabled="journalPage <= 1"
              @click="() => { journalPage--; loadJournal() }">{{ t('backoffice.finance.prev') }}</AppButton>
            <AppButton variant="outline" size="sm" :disabled="journalPage * 30 >= journalTotal"
              @click="() => { journalPage++; loadJournal() }">{{ t('backoffice.finance.next') }}</AppButton>
          </div>
        </div>
      </div>
    </AppCard>

    <!-- ══ NEW MANUAL JOURNAL ENTRY MODAL ══ -->
    <AppModal :open="newJournalModal.open" :title="`✍️ ${t('backoffice.finance.journal.newEntry.title')}`"
      size="lg" @close="newJournalModal.open = false">
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.entryDate') }}
            <input v-model="newJournalModal.entryDate" type="date"
              class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
          </label>
          <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.reference') }}
            <input v-model="newJournalModal.reference"
              :placeholder="t('backoffice.finance.journal.newEntry.referencePlaceholder')"
              class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
          </label>
        </div>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.journal.newEntry.description') }}
          <input v-model="newJournalModal.description"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>

        <div class="space-y-2">
          <div class="grid grid-cols-12 gap-2 text-xs font-semibold text-gray-500 dark:text-gray-400 px-1">
            <span class="col-span-5">{{ t('backoffice.finance.journal.account') }}</span>
            <span class="col-span-3">{{ t('backoffice.finance.journal.debit') }}</span>
            <span class="col-span-3">{{ t('backoffice.finance.journal.credit') }}</span>
          </div>
          <div v-for="(line, i) in newJournalModal.lines" :key="i" class="grid grid-cols-12 gap-2 items-center">
            <select v-model.number="line.accountId" class="col-span-5 min-h-[44px] rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-2 py-2 text-sm">
              <option :value="null">{{ t('backoffice.finance.journal.newEntry.selectAccount') }}</option>
              <option v-for="acc in allAccountOptions" :key="acc.id" :value="acc.id">{{ acc.code }} — {{ acc.name }}</option>
            </select>
            <input v-model="line.debit" type="number" min="0" step="0.01" placeholder="0.00"
              class="col-span-3 min-h-[44px] rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-2 py-2 text-sm tabular-nums" />
            <input v-model="line.credit" type="number" min="0" step="0.01" placeholder="0.00"
              class="col-span-3 min-h-[44px] rounded-xl border border-stone-200 dark:border-border bg-white dark:bg-surface px-2 py-2 text-sm tabular-nums" />
            <button type="button" class="col-span-1 text-danger disabled:opacity-30" :disabled="newJournalModal.lines.length <= 2"
              @click="removeJournalLine(i)">✕</button>
          </div>
          <button type="button" class="text-sm font-semibold text-primary-700 dark:text-primary-400" @click="addJournalLine">
            + {{ t('backoffice.finance.journal.newEntry.addLine') }}
          </button>
        </div>

        <div class="flex items-center justify-between rounded-xl px-3 py-2 text-sm font-bold"
          :class="newJournalIsBalanced ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'">
          <span>{{ t('backoffice.finance.journal.newEntry.totalDebit') }}: {{ formatNumber(newJournalTotalDebit) }}</span>
          <span>{{ t('backoffice.finance.journal.newEntry.totalCredit') }}: {{ formatNumber(newJournalTotalCredit) }}</span>
          <span>{{ newJournalIsBalanced ? '✓' : '⚠️' }}</span>
        </div>
        <p v-if="newJournalModal.error" class="text-sm text-red-600 dark:text-red-400">{{ newJournalModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2">
          <AppButton variant="ghost" class="flex-1" @click="newJournalModal.open = false">{{ t('backoffice.finance.cancel') }}</AppButton>
          <AppButton class="flex-1" :disabled="!newJournalIsBalanced" :loading="newJournalModal.saving" @click="confirmNewJournalEntry">
            {{ t('backoffice.finance.journal.newEntry.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
