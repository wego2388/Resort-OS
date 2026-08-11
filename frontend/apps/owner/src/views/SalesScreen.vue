<script setup lang="ts">
/**
 * SalesScreen — Phase 6 + 7b + 7d
 * tabs: المطعم | الشاطئ | فنادق B2B | الخصومات
 * DateRangePicker يتحكم في date_from/date_to لكل tab
 */
import { ref, computed, watch } from 'vue'
import {
  useOwnerSales,
  useOwnerBeachPerformance,
  useOwnerChannelAnalytics,
  useOwnerDiscountAnalytics,
  useDetailSheet,
} from '../composables/useOwnerData'
import { fetchDiningItemDetail, fetchBeachTypeDetail } from '../api/owner'
import type { DiningItemDetailResponse, BeachTypeDetailResponse } from '../api/types'
import { formatMoney, formatMoneyFull, formatPct } from '../composables/useFormat'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'
import DateRangePicker from '../components/DateRangePicker.vue'
import DetailSheet from '../components/DetailSheet.vue'

const tabs = ['dining', 'beach', 'channels', 'discounts'] as const
type Tab = typeof tabs[number]
const activeTab = ref<Tab>('dining')
const tabLabels: Record<Tab, string> = {
  dining:    'المطعم',
  beach:     'الشاطئ',
  channels:  'فنادق B2B',
  discounts: 'الخصومات',
}

// الفترة المشتركة بين كل التابات
const dateRange = ref<{ date_from: string; date_to: string } | null>(null)

const salesParams = computed(() => ({
  outlet: 'dining' as const,
  date_from: dateRange.value?.date_from,
  date_to:   dateRange.value?.date_to,
}))

const beachParams = computed(() => ({
  date_from: dateRange.value?.date_from,
  date_to:   dateRange.value?.date_to,
}))

const channelParams = computed(() => ({
  date_from: dateRange.value?.date_from,
  date_to:   dateRange.value?.date_to,
}))

const discountParams = computed(() => ({
  date_from: dateRange.value?.date_from,
  date_to:   dateRange.value?.date_to,
}))

const { data: salesData,    loading: salesLoading,    error: salesError,    reload: salesReload,    updateParams: updateSales }    = useOwnerSales(salesParams)
const { data: beachData,    loading: beachLoading,    error: beachError,    reload: beachReload,    updateParams: updateBeach }    = useOwnerBeachPerformance(beachParams)
const { data: channelData,  loading: channelLoading,  error: channelError,  reload: channelReload,  updateParams: updateChannel }  = useOwnerChannelAnalytics(channelParams)
const { data: discountData, loading: discountLoading, error: discountError, reload: discountReload, updateParams: updateDiscount } = useOwnerDiscountAnalytics(discountParams)

function onDateChange(range: { date_from: string; date_to: string }) {
  dateRange.value = range
  updateSales(salesParams.value)
  updateBeach(beachParams.value)
  updateChannel(channelParams.value)
  updateDiscount(discountParams.value)
}

const abcColor: Record<string, string> = {
  A: 'text-owner-green',
  B: 'text-owner-amber',
  C: 'text-owner-muted',
}

const topItems = computed(() => salesData.value?.items.slice(0, 20) ?? [])

// ── تفاصيل التفاصيل (Phase 8) ─────────────────────────────────────────
const itemDetail = useDetailSheet<DiningItemDetailResponse>()
function openItemDetail(itemId: number) {
  itemDetail.open(() => fetchDiningItemDetail({
    item_id: itemId,
    date_from: dateRange.value?.date_from,
    date_to:   dateRange.value?.date_to,
  }))
}

const beachDetail = useDetailSheet<BeachTypeDetailResponse>()
function openBeachDetail(txType: string) {
  beachDetail.open(() => fetchBeachTypeDetail({
    tx_type: txType,
    date_from: dateRange.value?.date_from,
    date_to:   dateRange.value?.date_to,
  }))
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('ar-EG', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const orderTypeLabel: Record<string, string> = {
  dine_in: 'صالة', takeaway: 'تيك أواي', delivery: 'توصيل', room_service: 'خدمة غرف',
}
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden">
    <!-- Tab bar -->
    <div class="flex bg-owner-card border-b border-owner-border overflow-x-auto" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="flex-shrink-0 px-4 py-3 text-sm font-semibold transition-colors touch-target whitespace-nowrap"
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

      <!-- Date Range Picker — مشترك لكل التابات -->
      <DateRangePicker @change="onDateChange" />

      <!-- ── المطعم ────────────────────────────────────────────── -->
      <template v-if="activeTab === 'dining'">
        <ErrorState v-if="salesError && !salesLoading" :message="salesError" @retry="salesReload" />
        <SkeletonCards v-else-if="salesLoading && !salesData" />

        <template v-else-if="salesData">
          <div class="owner-card">
            <div class="section-label">إجمالي إيراد المطعم</div>
            <div class="metric-value text-owner-green">
              {{ formatMoney(salesData.total_revenue) }}
            </div>
            <div class="text-xs text-owner-muted mt-1">
              {{ salesData.period_from }} ← {{ salesData.period_to }}
              <span v-if="salesData.is_provisional" class="text-owner-amber ml-2">⏳ مؤقت</span>
            </div>
          </div>

          <div class="owner-card">
            <div class="section-label mb-3">أداء الأصناف</div>
            <div v-if="topItems.length === 0" class="text-xs text-owner-muted text-center py-4">
              لا توجد مبيعات في هذه الفترة
            </div>
            <div v-else class="space-y-1">
              <div class="grid grid-cols-12 gap-1 text-xs text-owner-muted pb-2 border-b border-owner-border">
                <span class="col-span-5">الصنف</span>
                <span class="col-span-2 text-center">تصنيف</span>
                <span class="col-span-2 text-left">كمية</span>
                <span class="col-span-3 text-left">إيراد</span>
              </div>
              <button
                v-for="item in topItems"
                :key="item.item_id"
                class="w-full grid grid-cols-12 gap-1 py-2 border-b border-owner-border/50 last:border-0 text-xs text-right active:bg-owner-card transition-colors rounded-lg -mx-1 px-1"
                @click="openItemDetail(item.item_id)"
              >
                <div class="col-span-5">
                  <div class="font-semibold text-owner-text truncate">{{ item.name }}</div>
                  <div v-if="item.margin_pct != null" class="text-owner-muted mt-0.5">
                    هامش {{ formatPct(item.margin_pct) }}
                  </div>
                </div>
                <div class="col-span-2 flex items-center justify-center">
                  <span
                    v-if="item.abc_class"
                    class="font-bold text-sm"
                    :class="abcColor[item.abc_class] ?? 'text-owner-muted'"
                  >{{ item.abc_class }}</span>
                  <span v-else class="text-owner-muted">—</span>
                </div>
                <div class="col-span-2 flex items-center font-mono text-owner-muted">{{ item.quantity_sold }}</div>
                <div class="col-span-3 flex items-center justify-between font-mono text-owner-text font-semibold">
                  <span>{{ formatMoney(item.revenue) }}</span>
                  <span class="text-owner-muted" aria-hidden="true">‹</span>
                </div>
              </button>
            </div>
            <div class="mt-3 pt-3 border-t border-owner-border flex gap-4 text-xs text-owner-muted">
              <span><span class="text-owner-green font-bold">A</span> = 80% من الإيراد</span>
              <span><span class="text-owner-amber font-bold">B</span> = 15%</span>
              <span><span class="text-owner-muted font-bold">C</span> = 5%</span>
            </div>
          </div>
        </template>
      </template>

      <!-- ── الشاطئ ────────────────────────────────────────────── -->
      <template v-else-if="activeTab === 'beach'">
        <ErrorState v-if="beachError && !beachLoading" :message="beachError" @retry="beachReload" />
        <SkeletonCards v-else-if="beachLoading && !beachData" />

        <template v-else-if="beachData">
          <div class="owner-card">
            <div class="section-label">إجمالي إيراد الشاطئ</div>
            <div class="metric-value text-owner-green">{{ formatMoney(beachData.total_revenue) }}</div>
            <div class="text-xs text-owner-muted mt-1">
              {{ beachData.total_count }} تذكرة ·
              {{ beachData.period_from }} ← {{ beachData.period_to }}
            </div>
          </div>
          <div class="owner-card">
            <div class="section-label mb-3">أنواع التذاكر</div>
            <div v-if="beachData.ticket_types.length === 0" class="text-xs text-owner-muted text-center py-4">
              لا توجد تذاكر في هذه الفترة
            </div>
            <div v-else class="space-y-2">
              <button
                v-for="row in beachData.ticket_types"
                :key="row.tx_type"
                class="w-full flex items-center justify-between py-2 border-b border-owner-border last:border-0 text-right active:bg-owner-card transition-colors rounded-lg -mx-1 px-1"
                @click="openBeachDetail(row.tx_type)"
              >
                <div>
                  <div class="text-sm font-semibold text-owner-text">{{ row.tx_type }}</div>
                  <div class="text-xs text-owner-muted">{{ row.count }} تذكرة · متوسط {{ formatMoney(row.avg_unit_price) }}</div>
                </div>
                <div class="flex items-center gap-1">
                  <span class="font-mono font-bold text-owner-green">{{ formatMoney(row.total_amount) }}</span>
                  <span class="text-owner-muted" aria-hidden="true">‹</span>
                </div>
              </button>
            </div>
          </div>
        </template>
      </template>

      <!-- ── فنادق B2B ──────────────────────────────────────────── -->
      <template v-else-if="activeTab === 'channels'">
        <ErrorState v-if="channelError && !channelLoading" :message="channelError" @retry="channelReload" />
        <SkeletonCards v-else-if="channelLoading && !channelData" />

        <template v-else-if="channelData">
          <!-- ملخص -->
          <div class="owner-card">
            <div class="section-label">إجمالي قنوات B2B</div>
            <div class="grid grid-cols-3 gap-3 mt-2">
              <div class="text-center">
                <div class="metric-value text-owner-text text-xl">{{ channelData.total_checkins }}</div>
                <div class="text-xs text-owner-muted">دخول</div>
              </div>
              <div class="text-center">
                <div class="metric-value text-owner-green text-xl">{{ formatMoney(channelData.total_beach_revenue) }}</div>
                <div class="text-xs text-owner-muted">إيراد شاطئ</div>
              </div>
              <div class="text-center">
                <div class="metric-value text-owner-amber text-xl">{{ formatMoney(channelData.total_fnb_attach) }}</div>
                <div class="text-xs text-owner-muted">مطعم مرافق</div>
              </div>
            </div>
          </div>

          <div v-if="channelData.contracts.length === 0" class="owner-card text-center py-6">
            <div class="text-sm text-owner-muted">لا توجد عقود B2B نشطة في هذه الفترة</div>
          </div>

          <!-- بطاقة لكل فندق -->
          <div
            v-for="contract in channelData.contracts"
            :key="contract.contract_id"
            class="owner-card"
          >
            <div class="flex items-start justify-between mb-2">
              <div>
                <div class="text-sm font-bold text-owner-text">{{ contract.hotel_name }}</div>
                <div class="text-xs text-owner-muted mt-0.5">{{ contract.period_checkins }} دخول</div>
              </div>
              <div class="text-right">
                <div class="font-mono font-bold text-owner-green">{{ formatMoney(contract.period_revenue) }}</div>
                <div v-if="contract.is_overdue" class="overdue-badge mt-0.5 inline-block">متأخر</div>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-xs mt-2 pt-2 border-t border-owner-border">
              <div>
                <div class="text-owner-muted">ذمم مستحقة</div>
                <div class="font-mono font-semibold" :class="contract.is_overdue ? 'text-owner-red' : 'text-owner-text'">
                  {{ formatMoney(contract.outstanding) }}
                </div>
              </div>
              <div>
                <div class="text-owner-muted">مطعم مرافق</div>
                <div class="font-mono font-semibold text-owner-amber">{{ formatMoney(contract.fnb_attach) }}</div>
              </div>
              <div>
                <div class="text-owner-muted">متوسط مطعم / دخول</div>
                <div class="font-mono text-owner-text">{{ formatMoney(contract.fnb_avg_per_checkin) }}</div>
              </div>
              <div v-if="contract.credit_limit">
                <div class="text-owner-muted">حد الائتمان</div>
                <div class="font-mono text-owner-text">{{ formatMoney(contract.credit_limit) }}</div>
              </div>
            </div>
          </div>
        </template>
      </template>

      <!-- ── الخصومات ──────────────────────────────────────────── -->
      <template v-else-if="activeTab === 'discounts'">
        <ErrorState v-if="discountError && !discountLoading" :message="discountError" @retry="discountReload" />
        <SkeletonCards v-else-if="discountLoading && !discountData" />

        <template v-else-if="discountData">
          <!-- ملخص إجمالي -->
          <div class="owner-card">
            <div class="section-label">إجمالي الخصومات</div>
            <div class="metric-value text-owner-red">{{ formatMoney(discountData.total_discount) }}</div>
            <div class="text-xs text-owner-muted mt-1">
              {{ formatPct(discountData.discount_pct_of_revenue) }} من الإيراد ·
              {{ discountData.period_from }} ← {{ discountData.period_to }}
            </div>
          </div>

          <!-- أنواع الخصم -->
          <div class="owner-card">
            <div class="section-label mb-3">تفصيل أنواع الخصم</div>
            <div class="space-y-2">
              <div
                v-for="row in discountData.discount_types"
                :key="row.type"
                class="flex items-center justify-between py-1.5 border-b border-owner-border last:border-0"
              >
                <div>
                  <div class="text-sm text-owner-text">{{ row.type_label }}</div>
                  <div class="text-xs text-owner-muted">{{ row.order_count }} فاتورة</div>
                </div>
                <div class="text-right">
                  <div class="font-mono font-bold text-owner-red">{{ formatMoney(row.total_amount) }}</div>
                  <div class="text-xs text-owner-muted">{{ formatPct(row.pct_of_revenue) }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- خصومات يدوية per cashier -->
          <div v-if="discountData.manual_per_cashier.length > 0" class="owner-card">
            <div class="section-label mb-3">خصومات يدوية — أعلى كاشيرين</div>
            <div class="space-y-2">
              <div
                v-for="row in discountData.manual_per_cashier"
                :key="row.cashier_id"
                class="flex items-center justify-between py-1.5 border-b border-owner-border last:border-0"
              >
                <div class="text-sm text-owner-text">{{ row.cashier_name }}</div>
                <div class="text-right">
                  <div class="font-mono font-bold text-owner-red">{{ formatMoney(row.total_manual_discount) }}</div>
                  <div class="text-xs text-owner-muted">{{ row.order_count }} فاتورة</div>
                </div>
              </div>
            </div>
          </div>

          <!-- مجموعات العملاء بالاسم -->
          <div v-if="discountData.customer_groups.length > 0" class="owner-card">
            <div class="section-label mb-3">أداء مجموعات العملاء</div>
            <div class="space-y-4">
              <div
                v-for="group in discountData.customer_groups"
                :key="group.group_id"
                class="pb-3 border-b border-owner-border last:border-0"
              >
                <!-- رأس المجموعة -->
                <div class="flex items-center justify-between mb-2">
                  <div>
                    <div class="text-sm font-bold text-owner-text">{{ group.group_name }}</div>
                    <div class="text-xs text-owner-muted">
                      خصم {{ formatPct(group.discount_pct) }} · {{ group.member_count }} عميل
                    </div>
                  </div>
                  <div class="text-right">
                    <div class="font-mono font-semibold text-owner-green">{{ formatMoney(group.total_sales_after_discount) }}</div>
                    <div class="text-xs text-owner-muted">{{ group.total_invoices }} فاتورة</div>
                  </div>
                </div>

                <!-- أعضاء المجموعة — الاسم فقط (القاعدة: لا هاتف ولا email) -->
                <div v-if="group.members.length > 0" class="space-y-1">
                  <div
                    v-for="member in group.members"
                    :key="member.customer_id"
                    class="flex items-center justify-between py-1 text-xs"
                  >
                    <span class="text-owner-text">{{ member.full_name }}</span>
                    <div class="flex items-center gap-3 text-owner-muted font-mono">
                      <span>{{ member.invoice_count }} فاتورة</span>
                      <span class="text-owner-green">{{ formatMoney(member.total_sales) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </template>

    </div>

    <!-- تفاصيل صنف مطعم/كافيه -->
    <DetailSheet
      :open="itemDetail.isOpen.value"
      :title="itemDetail.data.value?.item_name ?? 'تفاصيل الصنف'"
      :subtitle="itemDetail.data.value ? `${itemDetail.data.value.total_quantity} قطعة · ${formatMoney(itemDetail.data.value.total_revenue)}` : undefined"
      :loading="itemDetail.loading.value"
      :error="itemDetail.error.value"
      @close="itemDetail.close()"
      @retry="itemDetail.retry()"
    >
      <div v-if="itemDetail.data.value?.transactions.length === 0" class="text-xs text-owner-muted text-center py-8">
        لا توجد طلبات في هذه الفترة
      </div>
      <div v-else class="space-y-1">
        <div
          v-for="tx in itemDetail.data.value?.transactions ?? []"
          :key="tx.order_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div class="min-w-0">
            <div class="font-semibold text-owner-text">{{ tx.order_number }}</div>
            <div class="text-owner-muted mt-0.5">
              {{ tx.outlet_name }} · {{ orderTypeLabel[tx.order_type] ?? tx.order_type }} · {{ formatDateTime(tx.ordered_at) }}
            </div>
          </div>
          <div class="text-left shrink-0">
            <div class="font-mono font-semibold text-owner-text">{{ formatMoneyFull(tx.line_total) }}</div>
            <div class="text-owner-muted">{{ tx.quantity }} × {{ formatMoney(tx.unit_price) }}</div>
          </div>
        </div>
      </div>
    </DetailSheet>

    <!-- تفاصيل نوع تذكرة شاطئ -->
    <DetailSheet
      :open="beachDetail.isOpen.value"
      :title="beachDetail.data.value?.tx_type ?? 'تفاصيل التذاكر'"
      :subtitle="beachDetail.data.value ? `${beachDetail.data.value.total_count} تذكرة · ${formatMoney(beachDetail.data.value.total_revenue)}` : undefined"
      :loading="beachDetail.loading.value"
      :error="beachDetail.error.value"
      @close="beachDetail.close()"
      @retry="beachDetail.retry()"
    >
      <div v-if="beachDetail.data.value?.transactions.length === 0" class="text-xs text-owner-muted text-center py-8">
        لا توجد معاملات في هذه الفترة
      </div>
      <div v-else class="space-y-1">
        <div
          v-for="tx in beachDetail.data.value?.transactions ?? []"
          :key="tx.transaction_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div>
            <div class="font-semibold text-owner-text">{{ new Date(tx.tx_date).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' }) }}</div>
            <div v-if="tx.cashier_name" class="text-owner-muted mt-0.5">{{ tx.cashier_name }}</div>
          </div>
          <div class="font-mono font-semibold text-owner-text">{{ formatMoneyFull(tx.total_amount) }}</div>
        </div>
      </div>
    </DetailSheet>
  </div>
</template>
