/**
 * Gate 3C — shared @resort-os/ui primitives: focus/label/ARIA basics that the
 * reference screens rely on. Covers AppInput (label association + error
 * announcement), AppButton (accessible name + loading/disabled), and AppModal
 * (dialog role, accessible name, focus-on-open, focus-return, Escape).
 */
import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { AppInput, AppButton, AppModal, MoneyInput } from '@resort-os/ui'

// Teleport(to="body") content is not auto-removed between tests — clear it so
// one modal's DOM never leaks into the next test's querySelector.
afterEach(() => { document.body.innerHTML = '' })

describe('AppInput', () => {
  it('associates its label with the input via for/id', () => {
    const wrapper = mount(AppInput, { props: { label: 'Password', modelValue: '' } })
    const input = wrapper.find('input')
    const label = wrapper.find('label')
    expect(label.attributes('for')).toBe(input.attributes('id'))
  })

  it('marks aria-invalid and announces the error when present', () => {
    const wrapper = mount(AppInput, {
      props: { label: 'Email', error: 'Required', modelValue: '' },
    })
    expect(wrapper.find('input').attributes('aria-invalid')).toBe('true')
    const err = wrapper.find('[role="alert"]')
    expect(err.exists()).toBe(true)
    expect(err.text()).toBe('Required')
  })

  it('emits update:modelValue on input', async () => {
    const wrapper = mount(AppInput, { props: { modelValue: '' } })
    await wrapper.find('input').setValue('hello')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['hello'])
  })
})

describe('MoneyInput', () => {
  it('associates its label and announced error with the amount input', () => {
    const wrapper = mount(MoneyInput, {
      props: { label: 'Amount', error: 'Required', modelValue: '' },
    })
    const input = wrapper.find('input')
    expect(wrapper.find('label').attributes('for')).toBe(input.attributes('id'))
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(input.attributes('aria-describedby')).toBe(wrapper.find('[role="alert"]').attributes('id'))
  })
})

describe('AppButton', () => {
  it('has an accessible name from its slot', () => {
    const wrapper = mount(AppButton, { slots: { default: 'Save' } })
    expect(wrapper.text()).toBe('Save')
  })

  it('is disabled and busy while loading', () => {
    const wrapper = mount(AppButton, { props: { loading: true }, slots: { default: 'Save' } })
    const btn = wrapper.find('button')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.attributes('aria-busy')).toBe('true')
  })
})

describe('AppModal', () => {
  it('renders as a labelled dialog when open', () => {
    mount(AppModal, {
      props: { open: true, title: 'Confirm' },
      attachTo: document.body,
    })
    const dialog = document.body.querySelector('[role="dialog"]')
    expect(dialog).not.toBeNull()
    expect(dialog!.getAttribute('aria-modal')).toBe('true')
    const labelledBy = dialog!.getAttribute('aria-labelledby')
    expect(labelledBy).toBeTruthy()
    expect(document.getElementById(labelledBy!)!.textContent).toBe('Confirm')
  })

  it('moves focus on initial open=true mount', async () => {
    mount(AppModal, {
      props: { open: true, title: 'Confirm' },
      slots: { default: '<button id="initial-action">Continue</button>' },
      attachTo: document.body,
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    const active = document.activeElement as HTMLElement | null
    expect(active?.closest('[role="dialog"]')).not.toBeNull()
    expect(active?.getAttribute('aria-label')).toBe('Close / إغلاق')
  })

  it('emits close on Escape', async () => {
    const wrapper = mount(AppModal, {
      props: { open: true, title: 'Confirm' },
      attachTo: document.body,
    })
    const dialog = document.body.querySelector('[role="dialog"]')!
    // Bubbles from the panel up to the overlay's keydown handler.
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('returns focus to the opener when closed', async () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    expect(document.activeElement).toBe(opener)

    const wrapper = mount(AppModal, {
      props: { open: false, title: 'Confirm' },
      attachTo: document.body,
    })
    await wrapper.setProps({ open: true })
    await wrapper.vm.$nextTick()
    await wrapper.setProps({ open: false })
    await wrapper.vm.$nextTick()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })

  it('returns focus when a conditionally mounted open dialog is unmounted', async () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    const wrapper = mount(AppModal, {
      props: { open: true, title: 'Confirm' },
      attachTo: document.body,
    })
    await wrapper.vm.$nextTick()
    wrapper.unmount()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })
})
