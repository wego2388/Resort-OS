import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { staffI18n } from '@resort-os/core/i18n/staff'
import PWAInstallButton from '../../components/PWAInstallButton.vue'

describe('PWAInstallButton', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('appears only after Chromium offers installation and invokes the prompt', async () => {
    const prompt = vi.fn().mockResolvedValue(undefined)
    const event = new Event('beforeinstallprompt', { cancelable: true })
    Object.defineProperties(event, {
      prompt: { value: prompt },
      userChoice: { value: Promise.resolve({ outcome: 'accepted', platform: 'web' }) },
    })
    const wrapper = mount(PWAInstallButton, {
      global: { plugins: [staffI18n] },
    })

    expect(wrapper.find('button').exists()).toBe(false)
    window.dispatchEvent(event)
    await nextTick()
    expect(wrapper.find('button').exists()).toBe(true)

    await wrapper.get('button').trigger('click')
    await Promise.resolve()
    await nextTick()
    expect(prompt).toHaveBeenCalledOnce()
    expect(wrapper.find('button').exists()).toBe(false)

    wrapper.unmount()
  })
})
