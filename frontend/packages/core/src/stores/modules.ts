import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'
import { ENDPOINTS } from '../api/endpoints'
import type { Module } from '../types'

export const useModulesStore = defineStore('modules', () => {
  const modules = ref<Module[]>([])

  const enabledModules = computed(() => modules.value.filter(m => m.enabled))

  function isEnabled(key: string): boolean {
    return modules.value.find(m => m.key === key)?.enabled ?? false
  }

  async function fetchEnabled() {
    const res = await api.get(ENDPOINTS.core.modules)
    // Backend returns a bare array (see Module type comment) — the `.modules`
    // fallback below is defensive only, the real shape is the array itself.
    modules.value = res.data.modules ?? res.data
  }

  return { modules, enabledModules, isEnabled, fetchEnabled }
})
