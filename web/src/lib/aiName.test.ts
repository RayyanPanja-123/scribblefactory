import { describe, expect, it } from 'vitest'
import { shortName } from './aiName'

describe('shortName', () => {
  it('keeps the thing, drops the details', () => {
    expect(shortName("A bright red baker's hat with a soft, floppy crown")).toBe('Red bakers hat')
    expect(shortName('A slow, proud bow with one arm across the chest')).toBe('Slow proud bow')
    expect(shortName('A grumpy goose with a long neck')).toBe('Grumpy goose')
    expect(shortName('A rainy bus stop at night with a flickering lamp')).toBe('Rainy bus stop')
    expect(shortName('A wooden maple syrup barrel with metal hoops, large enough for two thieves to carry')).toBe('Maple syrup barrel')
    expect(shortName('a cup of coffee')).toBe('Cup coffee')
  })
  it('stays short and never empty for real text', () => {
    expect(shortName('An extraordinarily magnificent internationally renowned chandelier').length).toBeLessThanOrEqual(24)
    expect(shortName('with a hat')).toBe('With hat')
    expect(shortName('   ')).toBe('')
  })
})
