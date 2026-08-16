<script setup lang="ts">
// 2026-08-16: خريطة وحدات حقيقية لاختيار الوحدة الفعلية وقت تأكيد/جدولة
// زيارة — قبل كده كان التخصيص أوتوماتيكي بالكامل (services.create_visit's
// find_available_unit)، الموظف مكانش شايف ولا مختار أي حاجة. مقصورة عمدًا
// على عقد عائم (contractUnitId فاضي، unitCapacity != 6) — عقد بوحدة ثابتة
// أو Family Compound بيتخصصوا أوتوماتيكيًا زي ما هما، الاختيار اليدوي هنا
// مش منطقي ليهم أصلًا (راجع services.create_visit).
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { LoadingState, EmptyState } from '@resort-os/ui'

const props = defineProps<{
  branchId: number | null
  unitType: string
  checkIn: string
  checkOut: string
  contractUnitId: number | null
  unitCapacity: number | null
  modelValue: number | null
}>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

const { t } = useI18n()

interface UnitAvailability { id: number; unit_number: string; unit_type: string; status: string; is_available: boolean }

const units = ref<UnitAvailability[]>([])
const loading = ref(false)
const loadError = ref('')

function applicable(): boolean {
  return !props.contractUnitId && props.unitCapacity !== 6
    && !!props.branchId && !!props.unitType && !!props.checkIn && !!props.checkOut
    && props.checkOut > props.checkIn
}

async function load() {
  if (!applicable()) { units.value = []; return }
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get('/api/v1/timeshare/units/availability', {
      params: {
        branch_id: props.branchId, unit_type: props.unitType,
        check_in: props.checkIn, check_out: props.checkOut,
      },
    })
    units.value = data
    // الوحدة المختارة سابقًا بقت مش متاحة (حد تاني حجزها) — امسح الاختيار
    // بدل ما نسيبه يفضل محدد لوحدة ملغاة من غير ما الموظف يلاحظ.
    if (props.modelValue && !units.value.some(u => u.id === props.modelValue && u.is_available)) {
      emit('update:modelValue', null)
    }
  } catch {
    loadError.value = t('backoffice.timeshare.unitPicker.loadError')
  } finally {
    loading.value = false
  }
}

watch(() => [props.branchId, props.unitType, props.checkIn, props.checkOut, props.contractUnitId, props.unitCapacity], load, { immediate: true })

function select(unit: UnitAvailability) {
  if (!unit.is_available) return
  emit('update:modelValue', props.modelValue === unit.id ? null : unit.id)
}
</script>

<template>
  <div v-if="contractUnitId || unitCapacity === 6" class="rounded-xl border border-stone-200 dark:border-border bg-stone-50 dark:bg-surface-2 px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
    🔒 {{ t('backoffice.timeshare.unitPicker.fixedUnitHint') }}
  </div>
  <div v-else-if="!checkIn || !checkOut" class="text-xs text-gray-500 dark:text-gray-400">
    {{ t('backoffice.timeshare.unitPicker.pickDatesFirst') }}
  </div>
  <div v-else class="space-y-2">
    <p class="text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.unitPicker.title') }}</p>
    <LoadingState v-if="loading" :label="t('backoffice.timeshare.unitPicker.loading')" />
    <p v-else-if="loadError" class="text-sm text-danger">{{ loadError }}</p>
    <EmptyState v-else-if="!units.length" icon="🏘️" :title="t('backoffice.timeshare.unitPicker.noUnits')" />
    <div v-else class="grid grid-cols-3 sm:grid-cols-4 gap-2">
      <button
        v-for="unit in units" :key="unit.id" type="button"
        :disabled="!unit.is_available"
        class="min-h-[44px] rounded-xl border px-2 py-1.5 text-sm font-bold transition-colors"
        :class="[
          modelValue === unit.id
            ? 'border-primary-600 bg-primary-100 text-primary-900 dark:bg-primary-900/40 dark:text-primary-200'
            : unit.is_available
              ? 'border-stone-200 dark:border-border bg-white dark:bg-surface text-gray-700 dark:text-gray-300 hover:border-primary-400'
              : 'border-stone-100 dark:border-border bg-stone-100 dark:bg-surface-2 text-gray-400 dark:text-gray-600 cursor-not-allowed',
        ]"
        @click="select(unit)"
      >
        {{ unit.unit_number }}
        <span v-if="unit.status === 'maintenance'" class="block text-[10px] font-normal">🛠️ {{ t('backoffice.timeshare.unitPicker.maintenance') }}</span>
        <span v-else-if="!unit.is_available" class="block text-[10px] font-normal">🔴 {{ t('backoffice.timeshare.unitPicker.occupied') }}</span>
      </button>
    </div>
    <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.unitPicker.autoAssignHint') }}</p>
  </div>
</template>
