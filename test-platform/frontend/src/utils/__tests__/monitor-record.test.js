import { describe, it, expect } from 'vitest'
import {
  UNKNOWN_ITEM_NAME,
  formatRecordTitle,
  normalizeRecord,
  normalizeRecords
} from '@/utils/monitorRecord'

describe('normalizeRecord：契约 item_name 归一化', () => {
  it('有 item_name 时原样保留并带 module_name', () => {
    const result = normalizeRecord({ id: 1, item_name: 'DDR 稳定性', module_name: 'DDR' })
    expect(result.item_name).toBe('DDR 稳定性')
    expect(result.module_name).toBe('DDR')
    expect(result.id).toBe(1)
  })

  it('缺失 item_name → 未知测试项（不再出现 undefined）', () => {
    const result = normalizeRecord({ id: 2, module_name: 'DDR' })
    expect(result.item_name).toBe('未知测试项')
    expect(result.item_name).not.toBe(undefined)
  })

  it('item_name 为 null / 空串 / 纯空白 → 未知测试项', () => {
    expect(normalizeRecord({ item_name: null }).item_name).toBe(UNKNOWN_ITEM_NAME)
    expect(normalizeRecord({ item_name: '' }).item_name).toBe(UNKNOWN_ITEM_NAME)
    expect(normalizeRecord({ item_name: '   ' }).item_name).toBe(UNKNOWN_ITEM_NAME)
  })

  it('误用旧字段 item.name 不会被读取（契约字段为 item_name）', () => {
    const result = normalizeRecord({ item: { name: '旧字段名' } })
    expect(result.item_name).toBe(UNKNOWN_ITEM_NAME)
  })

  it('module_name 缺失时回退 module.name，再兜底空串', () => {
    expect(normalizeRecord({ item_name: 'A', module: { name: 'M' } }).module_name).toBe('M')
    expect(normalizeRecord({ item_name: 'A' }).module_name).toBe('')
  })

  it('空/非对象入参安全兜底', () => {
    expect(normalizeRecord(null).item_name).toBe(UNKNOWN_ITEM_NAME)
    expect(normalizeRecord(undefined).item_name).toBe(UNKNOWN_ITEM_NAME)
    expect(normalizeRecord('bad').item_name).toBe(UNKNOWN_ITEM_NAME)
  })

  it('不修改入参对象', () => {
    const input = { item_name: 'DDR' }
    normalizeRecord(input)
    expect(input).toEqual({ item_name: 'DDR' })
  })
})

describe('normalizeRecords / formatRecordTitle', () => {
  it('批量归一化，非数组返回空数组', () => {
    expect(normalizeRecords([{ item_name: 'A' }, {}]).map((r) => r.item_name)).toEqual(['A', '未知测试项'])
    expect(normalizeRecords(null)).toEqual([])
    expect(normalizeRecords(undefined)).toEqual([])
  })

  it('标题在名称/模块缺失时均不出现 undefined', () => {
    expect(formatRecordTitle({ item_name: 'DDR', module_name: 'DDR' })).toBe('DDR / DDR')
    expect(formatRecordTitle({})).toBe('未知测试项')
    expect(formatRecordTitle({ module_name: 'M' })).toBe('M / 未知测试项')
    expect(formatRecordTitle(null)).toBe('未知测试项')
  })
})
