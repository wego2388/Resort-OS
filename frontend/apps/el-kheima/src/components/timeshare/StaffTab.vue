<script setup lang="ts">
// موظفو الملكية الجزئية (مدير الملكية الجزئية بيدير موظفينه بنفسه، منعزل
// عن شاشة الموظفين العامة) — استُخرج من TimeshareView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { AppButton, AppCard, AppBadge, AppModal, AppInput, EmptyState, LoadingState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface StaffMember { id: number; email: string; full_name: string; phone: string | null; is_active: boolean; must_change_password: boolean }
interface EligibleEmployee { id: number; employee_code: string; full_name: string; position: string; email: string | null; phone: string | null }

const toast = useToast()
const { t, locale } = useI18n()
const branchId = computed(() => props.branchId)

const timeshareStaff = ref<StaffMember[]>([])
const eligibleEmployees = ref<EligibleEmployee[]>([])
const staffLoading = ref(false)
const newStaffModal = ref({
  open: false, saving: false, employee_id: null as number | null, email: '', full_name: '', phone: '', error: '',
  result: null as { email: string; temporary_password: string } | null,
})

async function loadTimeshareStaff() {
  staffLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/staff', { params: { branch_id: branchId.value } })
    timeshareStaff.value = r.data
  } catch { toast.error(t('backoffice.timeshare.msg.loadStaffError')) } finally { staffLoading.value = false }
}

async function openNewStaffModal() {
  newStaffModal.value = { open: true, saving: false, employee_id: null, email: '', full_name: '', phone: '', error: '', result: null }
  try {
    const { data } = await api.get('/api/v1/timeshare/staff/eligible-employees', {
      params: { branch_id: branchId.value },
    })
    eligibleEmployees.value = data
  } catch {
    eligibleEmployees.value = []
    newStaffModal.value.error = t('backoffice.timeshare.msg.loadEligibleEmployeesError')
  }
}
function selectStaffEmployee() {
  const employee = eligibleEmployees.value.find(item => item.id === newStaffModal.value.employee_id)
  if (!employee) return
  newStaffModal.value.full_name = employee.full_name
  newStaffModal.value.email = employee.email ?? ''
  newStaffModal.value.phone = employee.phone ?? ''
}
async function createStaff() {
  if (!newStaffModal.value.employee_id || !newStaffModal.value.email.trim() || !newStaffModal.value.full_name.trim()) {
    newStaffModal.value.error = t('backoffice.timeshare.staffFormRequired')
    return
  }
  newStaffModal.value.saving = true
  newStaffModal.value.error = ''
  try {
    const r = await api.post('/api/v1/timeshare/staff', {
      branch_id: branchId.value, employee_id: newStaffModal.value.employee_id,
      email: newStaffModal.value.email.trim(),
      full_name: newStaffModal.value.full_name.trim(), phone: newStaffModal.value.phone.trim() || undefined,
      preferred_language: locale.value === 'en' ? 'en' : 'ar',
    })
    newStaffModal.value.result = r.data
    await loadTimeshareStaff()
  } catch (e) {
    newStaffModal.value.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.createStaffError')
  } finally { newStaffModal.value.saving = false }
}
async function toggleStaffActive(s: StaffMember) {
  try {
    const r = await api.patch(`/api/v1/timeshare/staff/${s.id}`, { is_active: !s.is_active })
    const idx = timeshareStaff.value.findIndex(x => x.id === s.id)
    if (idx !== -1) timeshareStaff.value[idx] = r.data
    toast.success(t('backoffice.timeshare.msg.staffStatusUpdated'))
  } catch (e) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.staffStatusError')) }
}

onMounted(loadTimeshareStaff)
</script>

<template>
  <div class="space-y-4">
    <AppButton @click="openNewStaffModal">➕ {{ t('backoffice.timeshare.newStaff') }}</AppButton>

    <LoadingState v-if="staffLoading" :label="t('backoffice.timeshare.loadingStaff')" />
    <AppCard v-else padding="none">
      <EmptyState v-if="!timeshareStaff.length" icon="🧑‍💼" :title="t('backoffice.timeshare.noResults')" />
      <div v-else class="divide-y divide-stone-100 dark:divide-border">
        <div v-for="s in timeshareStaff" :key="s.id" class="p-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="font-bold text-gray-900 dark:text-gray-100">{{ s.full_name }}</div>
            <div class="text-sm text-gray-600 dark:text-gray-300">{{ s.email }}{{ s.phone ? ` — ${s.phone}` : '' }}</div>
          </div>
          <div class="flex items-center gap-2">
            <AppBadge size="sm" :variant="s.is_active ? 'success' : 'neutral'">{{ s.is_active ? t('backoffice.timeshare.staffActive') : t('backoffice.timeshare.staffInactive') }}</AppBadge>
            <button @click="toggleStaffActive(s)"
              class="min-h-[44px] px-3 py-2 rounded-xl text-xs font-bold border"
              :class="s.is_active ? 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 border-red-200 dark:border-red-800 hover:bg-red-100' : 'bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 border-green-200 dark:border-green-800 hover:bg-green-100'">
              {{ s.is_active ? t('backoffice.timeshare.deactivate') : t('backoffice.timeshare.activate') }}
            </button>
          </div>
        </div>
      </div>
    </AppCard>

    <!-- ══ NEW TIMESHARE STAFF MODAL ══ -->
    <AppModal :open="newStaffModal.open" :title="`➕ ${t('backoffice.timeshare.newStaff')}`" size="sm" @close="newStaffModal.open = false">
      <div v-if="!newStaffModal.result" class="space-y-3">
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">
          {{ t('backoffice.timeshare.staffEmployee') }}
          <select v-model.number="newStaffModal.employee_id" @change="selectStaffEmployee"
            class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm">
            <option :value="null">{{ t('backoffice.timeshare.staffEmployeePlaceholder') }}</option>
            <option v-for="employee in eligibleEmployees" :key="employee.id" :value="employee.id">
              {{ employee.employee_code }} — {{ employee.full_name }} ({{ employee.position }})
            </option>
          </select>
        </label>
        <p v-if="!eligibleEmployees.length && !newStaffModal.error" class="text-sm text-amber-700 dark:text-amber-300">
          {{ t('backoffice.timeshare.noEligibleEmployees') }}
        </p>
        <AppInput v-model="newStaffModal.full_name" :label="t('backoffice.timeshare.staffFullName')" />
        <AppInput v-model="newStaffModal.email" type="email" :label="t('backoffice.timeshare.staffEmail')" />
        <AppInput v-model="newStaffModal.phone" :label="t('backoffice.timeshare.staffPhone')" />
        <p v-if="newStaffModal.error" class="text-sm text-red-600 dark:text-red-400">{{ newStaffModal.error }}</p>
        <AppButton class="w-full min-h-[44px]" :disabled="newStaffModal.saving || !eligibleEmployees.length" @click="createStaff">{{ newStaffModal.saving ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.createStaff') }}</AppButton>
      </div>
      <div v-else class="space-y-3">
        <div class="rounded-2xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 p-4 text-sm text-amber-800 dark:text-amber-200">
          {{ t('backoffice.timeshare.staffCredentialsWarning') }}
        </div>
        <p class="text-sm"><span class="font-bold">{{ t('backoffice.timeshare.staffEmail') }}:</span> {{ newStaffModal.result.email }}</p>
        <p class="text-sm"><span class="font-bold">{{ t('backoffice.timeshare.staffTempPassword') }}:</span> <code class="bg-stone-100 dark:bg-gray-800 px-2 py-1 rounded-lg">{{ newStaffModal.result.temporary_password }}</code></p>
        <AppButton class="w-full min-h-[44px]" @click="newStaffModal.open = false">{{ t('backoffice.timeshare.done') }}</AppButton>
      </div>
    </AppModal>
  </div>
</template>
