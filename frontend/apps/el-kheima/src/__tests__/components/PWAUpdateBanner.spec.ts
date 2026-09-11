import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { staffI18n } from '@resort-os/core/i18n/staff'
import PWAUpdateBanner from '../../components/PWAUpdateBanner.vue'

const needRefresh = ref(false)
const updateServiceWorker = vi.fn()

vi.mock('virtual:pwa-register/vue', () => ({
  useRegisterSW: () => ({ needRefresh, updateServiceWorker }),
}))

describe('PWAUpdateBanner', () => {
  it('stays hidden until a new service worker is waiting, then reloads on click', async () => {
    needRefresh.value = false
    const wrapper = mount(PWAUpdateBanner, {
      global: { plugins: [staffI18n] },
    })

    expect(wrapper.find('button').exists()).toBe(false)

    needRefresh.value = true
    await wrapper.vm.$nextTick()
    expect(wrapper.find('button').exists()).toBe(true)

    await wrapper.get('button').trigger('click')
    expect(updateServiceWorker).toHaveBeenCalledWith(true)

    wrapper.unmount()
  })
})
