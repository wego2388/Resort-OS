<script setup lang="ts">
// قائمة انتظار الملكية الجزئية (عميل بينتظر وحدة تفضى في فترة بعينها) —
// استُخرج من TimeshareView.vue (تقسيم الملفات الكبيرة، 2026-09-07).
// contracts هنا نسخة محلية مستقلة (لعرض اسم/رقم العقد بدل contract_id
// خام فقط) — نفس نمط تكرار الجلب المتبع في تقسيم FinanceView.vue/
// CRMView.vue/HRView.vue.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, EmptyState, LoadingState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Contract { id: number; contract_number: string; customer_name: string }
interface WaitlistEntry {
  id: number; branch_id: number; contract_id: number
  requested_start: string; requested_end: string; position: number
  status: string; notified_at: string | null; expires_at: string | null
}

const toast = useToast()
const { t } = useI18n()
const { formatDate } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)

function formatDateValue(d?: string) {
  if (!d) return '—'
  try { return formatDate(d, { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}

const contracts = ref<Contract[]>([])
const contractById = computed<Record<number, Contract>>(() =>
  Object.fromEntries(contracts.value.map(c => [c.id, c])),
)
async function loadContractsForNames() {
  try {
    const list: Contract[] = []
    let page = 1
    const size = 100
    while (true) {
      const response = await api.get('/api/v1/timeshare/contracts', {
        params: { branch_id: branchId.value, page, size },
      })
      const pageItems: Contract[] = response.data?.items ?? []
      list.push(...pageItems)
      if (list.length >= Number(response.data?.total ?? 0) || pageItems.length < size) break
      page += 1
    }
    contracts.value = list
  } catch { /* غير حرج — أسماء العقود هتفضل بس بالرقم لو فشل */ }
}

const waitlist = ref<WaitlistEntry[]>([])
const waitlistLoading = ref(false)
const updatingWaitlistId = ref<number | null>(null)

async function loadWaitlist() {
  waitlistLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/waitlist', { params: { branch_id: branchId.value } })
    waitlist.value = r.data ?? []
    await loadContractsForNames()
  } catch { toast.error(t('backoffice.timeshare.msg.loadWaitlistError')) }
  finally { waitlistLoading.value = false }
}

async function updateWaitlistStatus(entry: WaitlistEntry, newStatus: 'confirmed' | 'cancelled') {
  updatingWaitlistId.value = entry.id
  try {
    await api.patch(`/api/v1/timeshare/waitlist/${entry.id}`, { status: newStatus })
    waitlist.value = waitlist.value.filter(w => w.id !== entry.id)
    toast.success(t('backoffice.timeshare.msg.waitlistStatusUpdated'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.waitlistSaveError'))
  } finally { updatingWaitlistId.value = null }
}

onMounted(loadWaitlist)
</script>

<template>
  <div class="space-y-4">
    <LoadingState v-if="waitlistLoading" :label="t('backoffice.timeshare.loadingWaitlist')" />
    <AppCard v-else padding="none">
      <EmptyState v-if="!waitlist.length" icon="⏳" :title="t('backoffice.timeshare.noResults')" />
      <div v-else class="divide-y divide-stone-100 dark:divide-border">
        <div v-for="entry in waitlist" :key="entry.id" class="p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="font-bold text-gray-900 dark:text-gray-100">
              {{ contractById[entry.contract_id]?.customer_name ?? `#${entry.contract_id}` }}
              <span class="text-sm font-normal text-gray-500 dark:text-gray-400">— {{ contractById[entry.contract_id]?.contract_number }}</span>
            </div>
            <div class="text-sm text-gray-600 dark:text-gray-300">{{ formatDateValue(entry.requested_start) }} — {{ formatDateValue(entry.requested_end) }}</div>
            <div v-if="entry.status === 'notified' && entry.expires_at" class="text-xs text-amber-600 dark:text-amber-400">
              {{ t('backoffice.timeshare.waitlistExpiresAt', { date: formatDateValue(entry.expires_at) }) }}
            </div>
          </div>
          <div class="flex items-center gap-2">
            <AppBadge size="sm" :variant="entry.status === 'notified' ? 'warning' : 'info'">
              {{ t(`backoffice.timeshare.waitlistStatus.${entry.status}`, entry.status) }}
            </AppBadge>
            <template v-if="auth.hasRole('timeshare_admin')">
              <button @click="updateWaitlistStatus(entry, 'confirmed')" :disabled="updatingWaitlistId === entry.id"
                class="min-h-[44px] px-3 py-2 rounded-xl text-xs font-bold border bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 border-green-200 dark:border-green-800 hover:bg-green-100 disabled:opacity-40">
                ✅ {{ t('backoffice.timeshare.waitlistConfirm') }}
              </button>
              <button @click="updateWaitlistStatus(entry, 'cancelled')" :disabled="updatingWaitlistId === entry.id"
                class="min-h-[44px] px-3 py-2 rounded-xl text-xs font-bold border bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 border-red-200 dark:border-red-800 hover:bg-red-100 disabled:opacity-40">
                ❌ {{ t('backoffice.timeshare.waitlistCancel') }}
              </button>
            </template>
          </div>
        </div>
      </div>
    </AppCard>
  </div>
</template>
