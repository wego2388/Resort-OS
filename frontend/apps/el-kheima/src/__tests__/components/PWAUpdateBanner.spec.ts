import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { staffI18n } from '@resort-os/core/i18n/staff'
import PWAUpdateBanner from '../../components/PWAUpdateBanner.vue'
import { registerOperationalDraftGuard } from '../../composables/operationalDraftGuard'

const needRefresh = ref(false)
const updateServiceWorker = vi.fn()

vi.mock('virtual:pwa-register/vue', () => ({
  useRegisterSW: () => ({ needRefresh, updateServiceWorker }),
}))

describe('PWAUpdateBanner', () => {
  it('stays hidden until a new service worker is waiting, then protects drafts before reload', async () => {
    updateServiceWorker.mockReset()
    needRefresh.value = false
    const wrapper = mount(PWAUpdateBanner, {
      global: { plugins: [staffI18n] },
    })

    expect(wrapper.find('button').exists()).toBe(false)

    needRefresh.value = true
    await wrapper.vm.$nextTick()
    expect(wrapper.find('button').exists()).toBe(true)

    const blockedGuard = vi.fn().mockResolvedValue(false)
    const unregisterBlocked = registerOperationalDraftGuard(blockedGuard)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(blockedGuard).toHaveBeenCalledWith('app-update')
    expect(updateServiceWorker).not.toHaveBeenCalled()
    unregisterBlocked()

    const acceptedGuard = vi.fn().mockResolvedValue(true)
    const unregisterAccepted = registerOperationalDraftGuard(acceptedGuard)
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(updateServiceWorker).toHaveBeenCalledWith(true)
    unregisterAccepted()

    wrapper.unmount()
  })
})
