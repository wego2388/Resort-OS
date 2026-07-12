<script setup lang="ts">
// Grant/deny indicator for a single permission — for the permissions catalog
// (`GET /permissions/catalog`, `/admin/permissions` screen, super_admin
// only, see CLAUDE.md §18) where each of the 10 sensitive operations gets
// rendered as granted/denied per role. Deliberately a *display* component:
// it never decides who has what — that stays server-side (require_permission
// is "the sole governor", CLAUDE.md is explicit that no client should ever
// gate an action on this instead of the actual API 403).
import { computed } from 'vue'
import AppIcon from './Icon.vue'

const props = defineProps<{ granted: boolean; label?: string }>()

const classes = computed(() => props.granted
  ? 'bg-success/10 text-success'
  : 'bg-danger/10 text-danger')
</script>

<template>
  <span :class="['inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium', classes]">
    <AppIcon :name="granted ? 'check' : 'close'" size="xs" />
    <span v-if="label">{{ label }}</span>
    <span v-else>{{ granted ? 'مسموح' : 'غير مسموح' }}</span>
  </span>
</template>
