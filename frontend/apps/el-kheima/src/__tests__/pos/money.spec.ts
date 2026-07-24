import { describe, expect, it } from 'vitest'
import {
  cashPresetMinorValues,
  minorToMoney,
  moneyToMinor,
  remainingMinor,
} from '../../components/dining-pos/money'

describe('POS money helpers', () => {
  it('converts cashier input to exact integer minor units', () => {
    expect(moneyToMinor('123.45')).toBe(12_345)
    expect(moneyToMinor('123,4')).toBe(12_340)
    expect(moneyToMinor('.5')).toBe(50)
    expect(moneyToMinor(0)).toBe(0)
  })

  it('rejects unsafe or over-precise input', () => {
    expect(moneyToMinor('1.001')).toBeNull()
    expect(moneyToMinor('-1')).toBeNull()
    expect(moneyToMinor('not money')).toBeNull()
    expect(moneyToMinor(Number.MAX_SAFE_INTEGER)).toBeNull()
  })

  it('formats minor units deterministically', () => {
    expect(minorToMoney(12_345)).toBe('123.45')
    expect(minorToMoney(5)).toBe('0.05')
    expect(minorToMoney(-5)).toBe('-0.05')
  })

  it('keeps split-tender allocation exact without float drift', () => {
    expect(remainingMinor('100.00', ['33.33', '33.33', '33.34'])).toBe(0)
    expect(remainingMinor('100.00', ['25.25', '50.00'])).toBe(2_475)
    expect(remainingMinor('100.00', ['70.00', '40.00'])).toBe(-1_000)
  })

  it('offers the exact total followed by useful rounded cash presets', () => {
    expect(cashPresetMinorValues('123.45')).toEqual([12_345, 15_000, 20_000, 50_000])
    expect(cashPresetMinorValues('100.00')).toEqual([10_000, 20_000, 50_000])
  })
})
