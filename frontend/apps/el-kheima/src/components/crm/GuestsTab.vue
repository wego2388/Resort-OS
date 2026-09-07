<script setup lang="ts">
// بروفايلات الضيوف (تكامل PMS checkout — للعرض فقط) — استُخرج من
// CRMView.vue (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, parseApiTimestamp } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface GuestProfile {
  id: number; full_name: string; phone: string; email?: string; nationality?: string
  total_visits: number; avg_spend: number; vip_flag: boolean; last_stay?: string | null
}

const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn } = useStaffFormat()
const toast = useToast()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const guestProfiles = ref<GuestProfile[]>([])
const guestVipOnly = ref(false)

function fmtDate(d?: string | null) {
  if (!d) return '—'
  try { return fmtDateFn(parseApiTimestamp(d)) } catch { return d }
}

async function loadGuestProfiles() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/guest-profiles', { params: { branch_id: branchId.value, vip_only: guestVipOnly.value } })
    guestProfiles.value = res.data
  } catch { toast.error(t('backoffice.crm.msg.loadGuestsError')) }
  finally { loading.value = false }
}

onMounted(loadGuestProfiles)
</script>

<template>
  <div>
    <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">
      {{ t('backoffice.crm.guestProfilesHint') }}
    </p>
    <div class="flex justify-end mb-3">
      <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
        <input type="checkbox" v-model="guestVipOnly" @change="loadGuestProfiles" />
        {{ t('backoffice.crm.vipOnly') }}
      </label>
    </div>
    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
      <table class="w-full min-w-[500px]">
        <thead class="bg-stone-50 dark:bg-gray-800/60">
          <tr>
            <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.guest') }}</th>
            <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.visitCount') }}</th>
            <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.avgSpend') }}</th>
            <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.lastStay') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in guestProfiles" :key="g.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <span v-if="g.vip_flag" class="text-amber-500 text-sm">⭐</span>
                <div>
                  <div class="font-medium text-gray-900 dark:text-gray-100 text-sm">{{ g.full_name }}</div>
                  <div class="text-xs text-gray-400 dark:text-gray-400">{{ g.phone }}</div>
                </div>
              </div>
            </td>
            <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 font-medium">{{ g.total_visits }}</td>
            <td class="px-4 py-3 text-sm font-bold text-blue-700 dark:text-blue-300">{{ formatNumber(g.avg_spend) }} {{ t('backoffice.crm.egp') }}</td>
            <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ fmtDate(g.last_stay) }}</td>
          </tr>
          <tr v-if="guestProfiles.length === 0">
            <td colspan="4" class="px-4 py-8">
              <EmptyState icon="🏨" :title="t('backoffice.crm.noGuestProfiles')" :subtitle="t('backoffice.crm.noGuestProfilesHint')" />
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </AppCard>
  </div>
</template>
