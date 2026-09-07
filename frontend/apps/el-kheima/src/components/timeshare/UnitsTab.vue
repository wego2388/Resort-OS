<script setup lang="ts">
// إدارة مخزون وحدات الملكية الجزئية — استُخرج من TimeshareView.vue (تقسيم
// الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { AppButton, AppCard, AppBadge, AppModal, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface TimeshareUnit { id: number; branch_id: number; unit_number: string; unit_type: string; status: string; notes?: string | null }

const toast = useToast()
const { t } = useI18n()
const branchId = computed(() => props.branchId)

function roomTypeLabel(type: string): string {
  return t(`backoffice.timeshare.unitTypes.${type}`, type)
}
function roomTypeBadge(type: string) {
  const m: Record<string, string> = {
    'Studio': 'bg-sky-100 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300',
    'Chalet': 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300',
  }
  return `text-xs px-2 py-1 rounded-full font-bold ${m[type] || 'bg-stone-100 dark:bg-gray-700 text-stone-600 dark:text-stone-300'}`
}

const units = ref<TimeshareUnit[]>([])

async function loadUnits() {
  try {
    const r = await api.get('/api/v1/timeshare/units', { params: { branch_id: branchId.value } })
    units.value = r.data ?? []
  } catch { toast.error(t('backoffice.timeshare.msg.loadUnitsError')) }
}

const newUnitModal = ref(false)
const newUnitForm = ref({ unit_number: '', unit_type: 'Studio', notes: '' })
const savingUnit = ref(false)
const togglingUnitId = ref<number | null>(null)

function openNewUnitModal() {
  newUnitForm.value = { unit_number: '', unit_type: 'Studio', notes: '' }
  newUnitModal.value = true
}

async function submitNewUnit() {
  if (!newUnitForm.value.unit_number.trim()) {
    toast.error(t('backoffice.timeshare.msg.unitNumberRequired'))
    return
  }
  savingUnit.value = true
  try {
    const { data } = await api.post('/api/v1/timeshare/units', {
      branch_id: branchId.value,
      unit_number: newUnitForm.value.unit_number.trim(),
      unit_type: newUnitForm.value.unit_type,
      notes: newUnitForm.value.notes.trim() || null,
    })
    units.value = [...units.value, data]
    toast.success(t('backoffice.timeshare.msg.unitAdded'))
    newUnitModal.value = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.timeshare.msg.unitSaveError'))
  } finally { savingUnit.value = false }
}

async function toggleUnitMaintenance(unit: TimeshareUnit) {
  const nextStatus = unit.status === 'maintenance' ? 'available' : 'maintenance'
  togglingUnitId.value = unit.id
  try {
    const { data } = await api.patch(`/api/v1/timeshare/units/${unit.id}`, { status: nextStatus })
    units.value = units.value.map(u => (u.id === unit.id ? { ...u, ...data } : u))
    toast.success(t('backoffice.timeshare.msg.unitStatusUpdated'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.timeshare.msg.unitSaveError'))
  } finally { togglingUnitId.value = null }
}

onMounted(loadUnits)
</script>

<template>
  <div class="space-y-4">
    <AppButton @click="openNewUnitModal">➕ {{ t('backoffice.timeshare.newUnit') }}</AppButton>

    <AppCard padding="none">
      <EmptyState v-if="!units.length" icon="🏘️" :title="t('backoffice.timeshare.noResults')" />
      <div v-else class="divide-y divide-stone-100 dark:divide-border">
        <div v-for="u in units" :key="u.id" class="p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="font-bold text-gray-900 dark:text-gray-100">{{ u.unit_number }} <span :class="roomTypeBadge(u.unit_type)">{{ roomTypeLabel(u.unit_type) }}</span></div>
            <div v-if="u.notes" class="text-sm text-gray-500 dark:text-gray-400">{{ u.notes }}</div>
          </div>
          <div class="flex items-center gap-2">
            <AppBadge size="sm" :variant="u.status === 'available' ? 'success' : u.status === 'maintenance' ? 'warning' : 'info'">
              {{ t(`backoffice.timeshare.unitStatus.${u.status}`, u.status) }}
            </AppBadge>
            <button v-if="u.status !== 'occupied'" @click="toggleUnitMaintenance(u)" :disabled="togglingUnitId === u.id"
              class="min-h-[44px] px-3 py-2 rounded-xl text-xs font-bold border disabled:opacity-40"
              :class="u.status === 'maintenance' ? 'bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 border-green-200 dark:border-green-800 hover:bg-green-100' : 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border-amber-200 dark:border-amber-800 hover:bg-amber-100'">
              {{ u.status === 'maintenance' ? t('backoffice.timeshare.markAvailable') : t('backoffice.timeshare.markMaintenance') }}
            </button>
          </div>
        </div>
      </div>
    </AppCard>

    <!-- ══ NEW UNIT MODAL ══ -->
    <AppModal :open="newUnitModal" :title="`🏘️ ${t('backoffice.timeshare.newUnit')}`" size="sm" @close="newUnitModal = false">
      <div class="space-y-3">
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.unitNumber') }}
          <input v-model="newUnitForm.unit_number" type="text" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.unitType') }}
          <select v-model="newUnitForm.unit_type" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
            <option value="Studio">Studio</option>
            <option value="Chalet">Chalet</option>
          </select>
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.unitNotesOptional') }}
          <textarea v-model="newUnitForm.notes" rows="2" class="w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm resize-none" />
        </label>
        <AppButton class="w-full min-h-[44px]" :disabled="savingUnit" @click="submitNewUnit">{{ savingUnit ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.save') }}</AppButton>
      </div>
    </AppModal>
  </div>
</template>
