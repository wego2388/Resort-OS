<script setup lang="ts">
/**
 * Wizard — multi-step form shell.
 * الاستخدام الرئيسي: Timeshare contract creation (4 خطوات)، HR employee onboarding.
 *
 * <Wizard :steps="steps" v-model="activeStep" @complete="submit" @cancel="close">
 *   <template #step-info>...</template>
 *   <template #step-unit>...</template>
 * </Wizard>
 */
import { computed } from 'vue'
import AppButton from './Button.vue'
import AppIcon from './Icon.vue'

export interface WizardStep {
  id: string
  label: string
  sublabel?: string
  /** دالة validation اختيارية — لو رجعت false يتوقف التقدم للخطوة الجاية */
  validate?: () => boolean | Promise<boolean>
}

const props = withDefaults(defineProps<{
  steps: WizardStep[]
  modelValue: string
  /** السماح بالضغط على خطوة سابقة مكتملة للرجوع إليها */
  allowJump?: boolean
  loading?: boolean
  completeLabel?: string
  cancelLabel?: string
}>(), {
  allowJump: true,
  completeLabel: 'إنهاء',
  cancelLabel: 'إلغاء',
})

const emit = defineEmits<{
  'update:modelValue': [id: string]
  complete: []
  cancel: []
}>()

const currentIndex = computed(() => props.steps.findIndex(s => s.id === props.modelValue))
const isFirst = computed(() => currentIndex.value === 0)
const isLast  = computed(() => currentIndex.value === props.steps.length - 1)

function stepStatus(index: number): 'completed' | 'active' | 'upcoming' {
  if (index < currentIndex.value) return 'completed'
  if (index === currentIndex.value) return 'active'
  return 'upcoming'
}

async function goNext() {
  const current = props.steps[currentIndex.value]
  if (current?.validate) {
    const valid = await current.validate()
    if (!valid) return
  }
  if (isLast.value) {
    emit('complete')
  } else {
    emit('update:modelValue', props.steps[currentIndex.value + 1].id)
  }
}

function goPrev() {
  if (!isFirst.value) {
    emit('update:modelValue', props.steps[currentIndex.value - 1].id)
  }
}

function jumpTo(index: number) {
  if (!props.allowJump) return
  if (index < currentIndex.value) {
    emit('update:modelValue', props.steps[index].id)
  }
}
</script>

<template>
  <div class="flex flex-col gap-0">
    <!-- ── Step indicator ───────────────────────────────────────────────── -->
    <div class="flex items-center justify-between px-6 py-5 border-b border-stone-100 dark:border-border overflow-x-auto">
      <template v-for="(step, i) in steps" :key="step.id">
        <!-- Step node -->
        <div
          :class="[
            'flex flex-col items-center gap-1.5 min-w-0 shrink-0',
            allowJump && i < currentIndex ? 'cursor-pointer' : '',
          ]"
          @click="jumpTo(i)"
        >
          <!-- Circle -->
          <div :class="[
            'w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-all duration-base shrink-0',
            stepStatus(i) === 'completed' ? 'bg-success border-success text-white' :
            stepStatus(i) === 'active'    ? 'bg-primary-700 border-primary-700 text-white shadow-focus-ring' :
                                            'bg-white dark:bg-gray-700 border-stone-300 dark:border-gray-600 text-muted',
          ]">
            <AppIcon v-if="stepStatus(i) === 'completed'" name="check" size="sm" />
            <span v-else>{{ i + 1 }}</span>
          </div>
          <!-- Label -->
          <div class="text-center max-w-[80px]">
            <div :class="[
              'text-xs font-semibold truncate',
              stepStatus(i) === 'active' ? 'text-primary-700' :
              stepStatus(i) === 'completed' ? 'text-success' : 'text-muted',
            ]">{{ step.label }}</div>
            <div v-if="step.sublabel" class="text-[10px] text-muted truncate">{{ step.sublabel }}</div>
          </div>
        </div>

        <!-- Connector line -->
        <div v-if="i < steps.length - 1"
          :class="[
            'flex-1 h-0.5 mx-2 rounded transition-all duration-base',
            i < currentIndex ? 'bg-success' : 'bg-stone-200 dark:bg-gray-700',
          ]"
        />
      </template>
    </div>

    <!-- ── Step content ─────────────────────────────────────────────────── -->
    <div class="flex-1 min-h-0">
      <template v-for="step in steps" :key="step.id">
        <div v-if="modelValue === step.id">
          <slot :name="`step-${step.id}`" />
        </div>
      </template>
    </div>

    <!-- ── Footer navigation ────────────────────────────────────────────── -->
    <div class="flex items-center justify-between gap-3 px-6 py-4 border-t border-stone-100 dark:border-border bg-stone-50/50 dark:bg-gray-800/50">
      <AppButton variant="ghost" @click="emit('cancel')">{{ cancelLabel }}</AppButton>
      <div class="flex items-center gap-3">
        <AppButton v-if="!isFirst" variant="outline" @click="goPrev">
          <AppIcon name="chevron-right" size="sm" />
          السابق
        </AppButton>
        <AppButton variant="primary" :loading="loading" @click="goNext">
          <template v-if="isLast">
            <AppIcon name="check" size="sm" />
            {{ completeLabel }}
          </template>
          <template v-else>
            التالي
            <AppIcon name="chevron-left" size="sm" />
          </template>
        </AppButton>
      </div>
    </div>
  </div>
</template>
