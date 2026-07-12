<script setup lang="ts">
import { computed } from 'vue'
import { ICONS, type IconName } from '../icons/registry'
import {
  CheckCircleIcon as CheckCircleSolid,
  XCircleIcon as XCircleSolid,
  StarIcon as StarSolid,
  ExclamationTriangleIcon as ExclamationTriangleSolid,
  InformationCircleIcon as InformationCircleSolid,
  BellIcon as BellSolid,
} from '@heroicons/vue/24/solid'

// Only icons that plausibly need a "filled/emphasized" state (status +
// favorites + alerts) get a solid variant — everything else always renders
// outline regardless of the `solid` prop, which is the correct fallback
// (silently ignoring an inapplicable prop) rather than a hard error for a
// purely cosmetic toggle.
const SOLID_VARIANTS: Partial<Record<IconName, typeof CheckCircleSolid>> = {
  success: CheckCircleSolid,
  error: XCircleSolid,
  star: StarSolid,
  warning: ExclamationTriangleSolid,
  info: InformationCircleSolid,
  bell: BellSolid,
}

const props = withDefaults(defineProps<{
  name: IconName
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  solid?: boolean
  /** Decorative by default (aria-hidden). Pass a label when the icon is the only content of an interactive element (e.g. IconButton). */
  label?: string
}>(), { size: 'md' })

const component = computed(() => (props.solid && SOLID_VARIANTS[props.name]) || ICONS[props.name])

const sizeClass = computed(() => ({
  xs: 'w-3.5 h-3.5',
  sm: 'w-4 h-4',
  md: 'w-5 h-5',
  lg: 'w-6 h-6',
  xl: 'w-8 h-8',
}[props.size]))
</script>

<template>
  <component
    :is="component"
    :class="[sizeClass, 'shrink-0']"
    :aria-hidden="label ? undefined : 'true'"
    :aria-label="label"
    :role="label ? 'img' : undefined"
  />
</template>
