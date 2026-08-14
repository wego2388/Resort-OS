<script setup lang="ts">
/**
 * ExpensesScreen — Phase 6 + 7b
 * D-1: كل فئة مصروف كنسبة % من الإيراد مع variance flags
 * E-1: تركّز الإنفاق بالموردين
 * DateRangePicker للتحكم في الفترة (Decision 0004 §7b)
 */
import { ref, computed } from 'vue'
import { useOwnerExpenseAnalytics, useOwnerProcurementAnalytics, useDetailSheet } from '../composables/useOwnerData'
import { fetchExpenseDetail, fetchSupplierDetail } from '../api/owner'
import type { ExpenseDetailResponse, SupplierDetailResponse } from '../api/types'
import { formatMoney, formatMoneyFull, formatPct } from '../composables/useFormat'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'
import DateRangePicker from '../components/DateRangePicker.vue'
import DetailSheet from '../components/DetailSheet.vue'
import DataFreshness from '../components/DataFreshness.vue'

const tabs = ['expenses', 'procurement'] as const
type Tab = typeof tabs[number]
const activeTab = ref<Tab>('expenses')
const tabLabels: Record<Tab, string> = { expenses: 'المصروفات', procurement: 'المشتريات' }

const dateRange = ref<{ date_from: string; date_to: string } | null>(null)

const expParams  = computed(() => ({ date_from: dateRange.value?.date_from, date_to: dateRange.value?.date_to }))
const procParams = computed(() => ({ date_from: dateRange.value?.date_from, date_to: dateRange.value?.date_to }))

const { data: expData,  loading: expLoading,  error: expError,  reload: expReload,  updateParams: updateExp  } = useOwnerExpenseAnalytics(expParams)
const { data: procData, loading: procLoading, error: procError, reload: procReload, updateParams: updateProc } = useOwnerProcurementAnalytics(procParams)

const totalCurrentExpense = computed(() =>
  (expData.value?.expense_lines ?? []).reduce(
    (sum, line) => sum + (Number.parseFloat(line.current_amount) || 0),
    0,
  ),
)

function onDateChange(range: { date_from: string; date_to: string }) {
  dateRange.value = range
  updateExp(expParams.value)
  updateProc(procParams.value)
}

// ── تفاصيل التفاصيل (Phase 8) ─────────────────────────────────────────
const expenseDetail = useDetailSheet<ExpenseDetailResponse>()
function openExpenseDetail(accountCode: string) {
  expenseDetail.open(() => fetchExpenseDetail({
    account_code: accountCode,
    date_from: dateRange.value?.date_from,
    date_to:   dateRange.value?.date_to,
  }))
}

const supplierDetail = useDetailSheet<SupplierDetailResponse>()
function openSupplierDetail(supplierId: number) {
  supplierDetail.open(() => fetchSupplierDetail({
    supplier_id: supplierId,
    date_from: dateRange.value?.date_from,
    date_to:   dateRange.value?.date_to,
  }))
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' })
}

const poStatusLabel: Record<string, string> = { received: 'مستلم', partial: 'مستلم جزئيًا' }
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden">
    <!-- Tab bar -->
    <div class="flex bg-owner-card border-b border-owner-border" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="flex-1 py-3 text-sm font-semibold transition-colors touch-target"
        :class="activeTab === tab
          ? 'text-owner-green border-b-2 border-owner-green -mb-px'
          : 'text-owner-muted'"
        role="tab"
        :aria-selected="activeTab === tab"
        @click="activeTab = tab"
      >
        {{ tabLabels[tab] }}
      </button>
    </div>

    <div class="flex-1 overflow-y-auto overscroll-contain p-4 space-y-4">

      <!-- Date Range Picker -->
      <DateRangePicker @change="onDateChange" />

      <!-- ── المصروفات ──────────────────────────────────────────── -->
      <template v-if="activeTab === 'expenses'">
        <ErrorState v-if="expError && !expLoading" :message="expError" @retry="expReload" />
        <SkeletonCards v-else-if="expLoading && !expData" />

        <template v-else-if="expData">
          <div class="owner-card">
            <div class="section-label">ملخص الفترة</div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <div class="text-xs text-owner-muted">الإيراد</div>
                <div class="mt-1 text-lg font-bold text-owner-green">{{ formatMoney(expData.current_revenue) }}</div>
              </div>
              <div>
                <div class="text-xs text-owner-muted">فئات المصروف المسجّلة</div>
                <div class="mt-1 text-lg font-bold text-owner-amber">{{ formatMoney(totalCurrentExpense) }}</div>
              </div>
            </div>
            <div class="text-xs text-owner-muted mt-1">
              {{ expData.period_from }} ← {{ expData.period_to }}
              <span v-if="expData.is_provisional" class="text-owner-amber ml-2">⏳ مؤقت</span>
            </div>
          </div>

          <div v-if="expData.payroll" class="owner-card">
            <div class="section-label">الرواتب</div>
            <div class="metric-value text-owner-amber">{{ formatMoney(expData.payroll.total_net) }}</div>
            <div class="text-xs text-owner-muted mt-1">
              {{ formatPct(expData.payroll.payroll_pct) }} من الإيراد ·
              {{ expData.payroll.period_year }}/{{ expData.payroll.period_month }}
            </div>
          </div>

          <div class="owner-card">
            <div class="section-label mb-3">فئات المصروف</div>
            <div v-if="expData.expense_lines.length === 0" class="text-xs text-owner-muted text-center py-4">
              لا توجد مصروفات مسجّلة
            </div>
            <div v-else class="space-y-1">
              <button
                v-for="line in expData.expense_lines"
                :key="line.account_code"
                class="w-full py-2 border-b border-owner-border/50 last:border-0 text-right active:bg-owner-card transition-colors rounded-lg -mx-1 px-1"
                @click="openExpenseDetail(line.account_code)"
              >
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-2">
                    <span v-if="line.variance_flag" class="text-owner-red text-xs" title="variance">⚠</span>
                    <span class="text-sm text-owner-text">{{ line.account_name }}</span>
                  </div>
                  <span class="font-mono font-semibold text-owner-text">{{ formatMoney(line.current_amount) }}</span>
                </div>
                <div class="flex justify-between text-xs text-owner-muted mt-0.5">
                  <span>{{ formatPct(line.current_pct) }} من الإيراد</span>
                  <span
                    v-if="line.variance_delta != null"
                    :class="parseFloat(line.variance_delta) > 0 ? 'text-owner-red' : 'text-owner-green'"
                  >
                    {{ parseFloat(line.variance_delta) > 0 ? '↑' : '↓' }}
                    {{ formatPct(line.variance_delta) }} عن السابق
                  </span>
                </div>
              </button>
            </div>
          </div>
          <DataFreshness :at="expData.computed_at" :refresh="expReload" />
        </template>
      </template>

      <!-- ── المشتريات ─────────────────────────────────────────── -->
      <template v-else>
        <ErrorState v-if="procError && !procLoading" :message="procError" @retry="procReload" />
        <SkeletonCards v-else-if="procLoading && !procData" />

        <template v-else-if="procData">
          <div class="owner-card">
            <div class="section-label">إجمالي المشتريات</div>
            <div class="metric-value text-owner-amber">{{ formatMoney(procData.total_spend) }}</div>
            <div class="text-xs text-owner-muted mt-1">{{ procData.period_from }} ← {{ procData.period_to }}</div>
          </div>

          <div class="owner-card">
            <div class="section-label mb-3">الموردون</div>
            <div v-if="procData.suppliers.length === 0" class="text-xs text-owner-muted text-center py-4">
              لا توجد مشتريات
            </div>
            <div v-else class="space-y-2">
              <button
                v-for="sup in procData.suppliers"
                :key="sup.supplier_id"
                class="w-full flex items-center justify-between py-2 border-b border-owner-border last:border-0 text-right active:bg-owner-card transition-colors rounded-lg -mx-1 px-1"
                @click="openSupplierDetail(sup.supplier_id)"
              >
                <div>
                  <div class="flex items-center gap-2">
                    <span v-if="sup.concentration_flag" class="text-owner-red text-xs">⚠</span>
                    <span class="text-sm font-semibold text-owner-text">{{ sup.supplier_name }}</span>
                  </div>
                  <div class="text-xs text-owner-muted">{{ sup.order_count }} طلب · {{ formatPct(sup.spend_pct) }} من الإجمالي</div>
                </div>
                <div class="flex items-center gap-1">
                  <span class="font-mono font-bold text-owner-text">{{ formatMoney(sup.total_spend) }}</span>
                  <span class="text-owner-muted" aria-hidden="true">‹</span>
                </div>
              </button>
            </div>
          </div>

          <div v-if="procData.pr_po_variance.length > 0" class="owner-card">
            <div class="section-label mb-3">فرق التقدير والفعلي (PR vs PO)</div>
            <div class="space-y-2">
              <div
                v-for="row in procData.pr_po_variance"
                :key="row.product_id"
                class="flex items-center justify-between py-2 border-b border-owner-border last:border-0 text-xs"
              >
                <div>
                  <div class="font-semibold text-owner-text">{{ row.product_name }}</div>
                  <div class="text-owner-muted">مقدّر {{ formatMoney(row.estimated_cost) }}</div>
                </div>
                <div class="text-right">
                  <div class="font-mono text-owner-text">{{ formatMoney(row.actual_cost) }}</div>
                  <div :class="parseFloat(row.variance_amount) > 0 ? 'text-owner-red' : 'text-owner-green'">
                    {{ parseFloat(row.variance_amount) > 0 ? '+' : '' }}{{ formatMoney(row.variance_amount) }}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <DataFreshness :at="procData.computed_at" :refresh="procReload" />
        </template>
      </template>

    </div>

    <!-- تفاصيل فئة مصروف -->
    <DetailSheet
      :open="expenseDetail.isOpen.value"
      :title="expenseDetail.data.value?.account_name ?? 'تفاصيل المصروف'"
      :subtitle="expenseDetail.data.value ? formatMoney(expenseDetail.data.value.total_amount) : undefined"
      :loading="expenseDetail.loading.value"
      :error="expenseDetail.error.value"
      @close="expenseDetail.close()"
      @retry="expenseDetail.retry()"
    >
      <div v-if="expenseDetail.data.value?.lines.length === 0" class="text-xs text-owner-muted text-center py-8">
        لا توجد قيود في هذه الفترة
      </div>
      <div v-else class="space-y-1">
        <div
          v-for="line in expenseDetail.data.value?.lines ?? []"
          :key="line.entry_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div class="min-w-0">
            <div class="font-semibold text-owner-text truncate">{{ line.description }}</div>
            <div class="text-owner-muted mt-0.5">{{ line.reference }} · {{ formatDate(line.entry_date) }}</div>
          </div>
          <div class="font-mono font-semibold text-owner-text shrink-0">{{ formatMoneyFull(line.amount) }}</div>
        </div>
      </div>
    </DetailSheet>

    <!-- تفاصيل مورد -->
    <DetailSheet
      :open="supplierDetail.isOpen.value"
      :title="supplierDetail.data.value?.supplier_name ?? 'تفاصيل المورد'"
      :subtitle="supplierDetail.data.value ? `${supplierDetail.data.value.orders.length} أمر شراء · ${formatMoney(supplierDetail.data.value.total_amount)}` : undefined"
      :loading="supplierDetail.loading.value"
      :error="supplierDetail.error.value"
      @close="supplierDetail.close()"
      @retry="supplierDetail.retry()"
    >
      <div v-if="supplierDetail.data.value?.orders.length === 0" class="text-xs text-owner-muted text-center py-8">
        لا توجد أوامر شراء في هذه الفترة
      </div>
      <div v-else class="space-y-1">
        <div
          v-for="po in supplierDetail.data.value?.orders ?? []"
          :key="po.po_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div>
            <div class="font-semibold text-owner-text">{{ po.po_number }}</div>
            <div class="text-owner-muted mt-0.5">
              {{ poStatusLabel[po.status] ?? po.status }} · {{ po.item_count }} صنف · {{ formatDate(po.ordered_at) }}
            </div>
          </div>
          <div class="font-mono font-semibold text-owner-text">{{ formatMoneyFull(po.total_amount) }}</div>
        </div>
      </div>
    </DetailSheet>
  </div>
</template>
