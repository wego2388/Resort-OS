<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AppIcon } from '@resort-os/ui'
import { fetchOwnerMallSummary } from '../api/owner'
import type { OwnerMallSummaryResponse } from '../api/types'
import { formatMoney } from '../composables/useFormat'
import DataFreshness from '../components/DataFreshness.vue'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'

const data = ref<OwnerMallSummaryResponse | null>(null)
const loading = ref(true)
const error = ref('')

const statusLabel: Record<string, string> = {
  draft: 'مسودة',
  active: 'نشط',
  expired: 'منتهي',
  terminated: 'مفسوخ',
}

const statusClass: Record<string, string> = {
  draft: 'text-owner-muted border-owner-border',
  active: 'text-owner-green border-owner-green/30 bg-owner-green/10',
  expired: 'text-owner-amber border-owner-amber/30 bg-owner-amber/10',
  terminated: 'text-owner-red border-owner-red/30 bg-owner-red/10',
}

const hasOverdue = computed(() => Number(data.value?.overdue_receivables ?? 0) > 0)

function formatDate(value: string): string {
  const date = new Date(`${value}T12:00:00`)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('ar-EG', { day: 'numeric', month: 'short', year: 'numeric' })
}

function expiryLabel(days: number): string {
  if (days < 0) return `منتهي منذ ${Math.abs(days)} يوم`
  if (days === 0) return 'ينتهي اليوم'
  return `متبقي ${days} يوم`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchOwnerMallSummary()
  } catch {
    error.value = 'تعذّر تحميل بيانات المول وعقود الإيجار. تحقق من الاتصال ثم حاول مرة أخرى.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="flex-1 overflow-y-auto overscroll-contain">
    <div class="mx-auto max-w-5xl space-y-4 p-4 pb-6">
      <section class="owner-card" aria-labelledby="mall-title">
        <div class="flex items-start gap-3">
          <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-owner-green/10 text-owner-green">
            <AppIcon name="building" size="lg" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 id="mall-title" class="text-lg font-black text-owner-text">المول التجاري</h2>
            <p class="mt-1 text-xs leading-5 text-owner-muted">
              قراءة مباشرة لعقود Leasing والاستحقاقات والتحصيل، بدون بيانات مستأجر شخصية.
            </p>
          </div>
        </div>
      </section>

      <ErrorState v-if="error && !loading" :message="error" @retry="load" />
      <SkeletonCards v-else-if="loading && !data" />

      <template v-else-if="data">
        <section
          v-if="!data.registry_ready"
          class="owner-card border border-owner-amber/30 bg-owner-amber/10"
          aria-labelledby="mall-readiness-title"
        >
          <div class="flex items-start gap-3">
            <AppIcon name="warning" class="mt-0.5 shrink-0 text-owner-amber" />
            <div>
              <h3 id="mall-readiness-title" class="font-bold text-owner-text">سجل الوحدات والخريطة بانتظار الاعتماد</h3>
              <p class="mt-1 text-xs leading-5 text-owner-muted">
                لذلك لا نعرض إجمالي الوحدات أو الشاغر أو نسبة إشغال تخمينية. الأرقام أدناه تخص العقود والاستحقاقات المسجلة فعليًا فقط.
              </p>
            </div>
          </div>
        </section>

        <section aria-labelledby="mall-money-title">
          <div class="mb-2 flex items-center justify-between gap-3">
            <h3 id="mall-money-title" class="font-bold text-owner-text">حركة الإيجارات هذا الشهر حتى اليوم</h3>
            <span v-if="data.period.is_provisional" class="rounded-full bg-owner-amber/10 px-2 py-1 text-[11px] font-bold text-owner-amber">
              مبدئي
            </span>
          </div>
          <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <article class="owner-card min-w-0">
              <p class="text-xs text-owner-muted">مجدول حتى اليوم</p>
              <p class="mt-2 break-words font-mono text-lg font-black text-owner-text">{{ formatMoney(data.scheduled_rent) }}</p>
            </article>
            <article class="owner-card min-w-0">
              <p class="text-xs text-owner-muted">إيراد متحقق</p>
              <p class="mt-2 break-words font-mono text-lg font-black text-owner-green">{{ formatMoney(data.accrued_rent) }}</p>
            </article>
            <article class="owner-card min-w-0">
              <p class="text-xs text-owner-muted">متحصل فعليًا</p>
              <p class="mt-2 break-words font-mono text-lg font-black text-owner-green">{{ formatMoney(data.collected_rent) }}</p>
            </article>
            <article class="owner-card min-w-0">
              <p class="text-xs text-owner-muted">متأخر واجب التحصيل</p>
              <p class="mt-2 break-words font-mono text-lg font-black" :class="hasOverdue ? 'text-owner-red' : 'text-owner-text'">
                {{ formatMoney(data.overdue_receivables) }}
              </p>
            </article>
          </div>
        </section>

        <section class="grid gap-3 sm:grid-cols-3" aria-label="حالة عقود المول">
          <article class="owner-card text-center">
            <p class="text-2xl font-black text-owner-text">{{ data.total_contract_count }}</p>
            <p class="mt-1 text-xs text-owner-muted">عقد مسجل</p>
          </article>
          <article class="owner-card text-center">
            <p class="text-2xl font-black text-owner-green">{{ data.active_contract_count }}</p>
            <p class="mt-1 text-xs text-owner-muted">عقد نشط</p>
          </article>
          <article class="owner-card text-center">
            <p class="text-2xl font-black" :class="data.expiring_within_30_days ? 'text-owner-amber' : 'text-owner-text'">
              {{ data.expiring_within_30_days }}
            </p>
            <p class="mt-1 text-xs text-owner-muted">ينتهي خلال 30 يومًا</p>
          </article>
        </section>

        <section aria-labelledby="mall-contracts-title" class="space-y-3">
          <div>
            <h3 id="mall-contracts-title" class="font-bold text-owner-text">العقود المسجلة</h3>
            <p class="mt-1 text-xs text-owner-muted">وصف الوحدة كما هو محفوظ في العقد؛ ليس سجل وحدات المول المعتمد.</p>
          </div>

          <div v-if="data.contracts.length === 0" class="owner-card py-10 text-center">
            <AppIcon name="building" size="xl" class="mx-auto text-owner-muted" />
            <p class="mt-3 font-bold text-owner-text">لا توجد عقود إيجار مسجلة</p>
            <p class="mt-1 text-xs text-owner-muted">لا توجد بيانات تشغيلية نعرضها حاليًا.</p>
          </div>

          <article v-for="contract in data.contracts" v-else :key="contract.contract_id" class="owner-card">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h4 class="break-words font-bold text-owner-text">{{ contract.unit_description }}</h4>
                <p class="mt-1 font-mono text-xs text-owner-muted">{{ contract.contract_number }}</p>
              </div>
              <span class="shrink-0 rounded-full border px-2 py-1 text-[11px] font-bold" :class="statusClass[contract.status]">
                {{ statusLabel[contract.status] ?? contract.status }}
              </span>
            </div>

            <dl class="mt-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
              <div>
                <dt class="text-owner-muted">ينتهي</dt>
                <dd class="mt-1 font-semibold text-owner-text">{{ formatDate(contract.end_date) }}</dd>
                <dd class="mt-0.5 text-[11px] text-owner-muted">{{ expiryLabel(contract.days_until_expiry) }}</dd>
              </div>
              <div>
                <dt class="text-owner-muted">مجدول حتى اليوم</dt>
                <dd class="mt-1 font-mono font-semibold text-owner-text">{{ formatMoney(contract.scheduled_to_date) }}</dd>
              </div>
              <div>
                <dt class="text-owner-muted">مسدد على الجدول</dt>
                <dd class="mt-1 font-mono font-semibold text-owner-green">{{ formatMoney(contract.paid_to_date) }}</dd>
              </div>
              <div>
                <dt class="text-owner-muted">مستحق قائم</dt>
                <dd class="mt-1 font-mono font-semibold" :class="Number(contract.due_outstanding) > 0 ? 'text-owner-red' : 'text-owner-text'">
                  {{ formatMoney(contract.due_outstanding) }}
                </dd>
              </div>
            </dl>
          </article>
        </section>

        <DataFreshness :at="data.period.computed_at" :refresh="load" />
      </template>
    </div>
  </div>
</template>
