import { describe, it, expect } from 'vitest'
import {
  buildCompareRows,
  countStatuses,
  deriveTaskSummary,
  formatDurationSeconds,
  formatPassRate,
  normalizeDashboardOutcomes,
  normalizeSummary,
  toPassRate
} from '@/utils/stats'

describe('formatPassRate：null 与 0 区分', () => {
  it('null/undefined/空串 → 无有效结果', () => {
    expect(formatPassRate(null)).toBe('无有效结果')
    expect(formatPassRate(undefined)).toBe('无有效结果')
    expect(formatPassRate('')).toBe('无有效结果')
  })

  it('0 保留为 0%，100 为 100%', () => {
    expect(formatPassRate(0)).toBe('0%')
    expect(formatPassRate(100)).toBe('100%')
    expect(formatPassRate(50.5)).toBe('50.5%')
  })

  it('toPassRate 保留 0，非数值归一为 null', () => {
    expect(toPassRate(0)).toBe(0)
    expect(toPassRate('0')).toBe(0)
    expect(toPassRate(null)).toBeNull()
    expect(toPassRate(undefined)).toBeNull()
    expect(toPassRate('abc')).toBeNull()
  })
})

describe('formatDurationSeconds：耗时 0 不显示缺失', () => {
  it('0 → 0秒，null → —', () => {
    expect(formatDurationSeconds(0)).toBe('0秒')
    expect(formatDurationSeconds(null)).toBe('—')
    expect(formatDurationSeconds(undefined)).toBe('—')
    expect(formatDurationSeconds(65)).toBe('1分5秒')
  })
})

describe('countStatuses / normalizeSummary / deriveTaskSummary', () => {
  it('五类状态精确计数，0 保真', () => {
    const counts = countStatuses([
      { status: 'pass' },
      { status: 'pass' },
      { status: 'fail' },
      { status: 'skip' },
      { status: 'error' },
      { status: 'timeout' },
      { status: 'running' }
    ])
    expect(counts).toEqual({ pass: 2, fail: 1, skip: 1, error: 1, timeout: 1 })
    expect(countStatuses([])).toEqual({ pass: 0, fail: 0, skip: 0, error: 0, timeout: 0 })
  })

  it('normalizeSummary 优先 counts，其次契约字段，再兼容旧键', () => {
    expect(
      normalizeSummary({
        total_items: 6,
        pass: 99,
        counts: { pass: 2, fail: 1, skip: 2, error: 0, timeout: 1 },
        pass_rate: 50
      })
    ).toMatchObject({
      totalItems: 6,
      counts: { pass: 2, fail: 1, skip: 2, error: 0, timeout: 1 },
      passRate: 50
    })
    expect(
      normalizeSummary({ total_items: 3, pass: 1, fail: 0, skip: 2, error: 0, timeout: 0, pass_rate: null })
    ).toMatchObject({ counts: { pass: 1, fail: 0, skip: 2, error: 0, timeout: 0 }, passRate: null })
    expect(normalizeSummary({ passed: 4, failed: 1, skipped: 2, error: 0 }).counts).toMatchObject({
      pass: 4,
      fail: 1,
      skip: 2
    })
  })

  it('deriveTaskSummary 使用后端 pass_rate（null/0 保真）', () => {
    const results = [{ status: 'skip' }, { status: 'skip' }]
    expect(deriveTaskSummary({ total_items: 2, pass_rate: null }, results)).toMatchObject({
      totalItems: 2,
      passRate: null,
      counts: { pass: 0, fail: 0, skip: 2, error: 0, timeout: 0 }
    })
    expect(deriveTaskSummary({ total_items: 3, pass_rate: 0 }, [{ status: 'fail' }]).passRate).toBe(0)
  })
})

describe('normalizeDashboardOutcomes：不得把 completed 当 passed', () => {
  it('优先 task_outcomes 完整分列与 today.pass_rate', () => {
    const out = normalizeDashboardOutcomes({
      today: { tasks: 7, passed: 1, failed: 1, pass_rate: 50 },
      task_outcomes: {
        passed: 1,
        failed: 1,
        no_result: 2,
        execution_failed: 1,
        cancelled: 1,
        running: 1,
        pending: 0
      },
      devices: { total: 3, online: 2 }
    })
    expect(out).toEqual({
      tasks: 7,
      passed: 1,
      failed: 1,
      noResult: 2,
      executionFailed: 1,
      cancelled: 1,
      running: 1,
      pending: 0,
      passRate: 50,
      onlineDevices: 2
    })
  })

  it('仅有 completed 时不将 completed 作为 passed', () => {
    const out = normalizeDashboardOutcomes({
      today: { tasks: 5, completed: 5, failed: 0, pass_rate: null }
    })
    expect(out.passed).toBe(0)
    expect(out.passRate).toBeNull()
  })

  it('无数据时零值与 null', () => {
    const out = normalizeDashboardOutcomes({})
    expect(out.tasks).toBe(0)
    expect(out.passed).toBe(0)
    expect(out.passRate).toBeNull()
  })
})

describe('buildCompareRows：按 item_id 对齐，重名不互换', () => {
  it('重名不同 item_id 不合并、不互换', () => {
    const left = {
      task_id: 1,
      results: [{ item_id: 11, item_name: '同名项', module_name: 'M', status: 'pass', execution_time: 0 }]
    }
    const right = {
      task_id: 2,
      results: [{ item_id: 22, item_name: '同名项', module_name: 'M', status: 'fail', execution_time: 3 }]
    }
    const { rows } = buildCompareRows(left, right)
    expect(rows).toHaveLength(2)
    const leftRow = rows.find((r) => r.item_id === 11)
    const rightRow = rows.find((r) => r.item_id === 22)
    expect(leftRow).toMatchObject({ left_status: 'pass', right_status: null, comparable: false, verdict: 'not_comparable', left_time: 0 })
    expect(rightRow).toMatchObject({ left_status: null, right_status: 'fail', comparable: false, verdict: 'not_comparable' })
  })

  it('同一 item_id 不同名称仍按 item_id 对齐', () => {
    const left = { task_id: 1, results: [{ item_id: 5, item_name: '旧名', module_name: 'M', status: 'pass', execution_time: 0 }] }
    const right = { task_id: 2, results: [{ item_id: 5, item_name: '新名', module_name: 'M', status: 'pass', execution_time: 2 }] }
    const { rows } = buildCompareRows(left, right)
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ item_id: 5, comparable: true, same: true, verdict: 'same', left_time: 0, right_time: 2 })
  })

  it('状态不同 → different；缺失耗时保留 null', () => {
    const left = { task_id: 1, results: [{ item_id: 7, item_name: 'A', module_name: 'M', status: 'pass', execution_time: null }] }
    const right = { task_id: 2, results: [{ item_id: 7, item_name: 'A', module_name: 'M', status: 'fail', execution_time: 0 }] }
    const { rows } = buildCompareRows(left, right)
    expect(rows[0]).toMatchObject({ comparable: true, same: false, verdict: 'different', left_time: null, right_time: 0 })
  })
})
