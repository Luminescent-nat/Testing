import { describe, it, expect } from 'vitest'
import { NO_PLAN_TEXT, buildPlanPreview, extractCreatedTaskId } from '@/utils/aiTask'

describe('extractCreatedTaskId：创建响应 → 任务 ID', () => {
  it('契约 Task 对象返回正整数 id', () => {
    expect(extractCreatedTaskId({ id: 101, name: 'AI任务', device_serial: 'A133P-01' })).toBe(101)
    expect(extractCreatedTaskId({ id: 1 })).toBe(1)
  })

  it('id 缺失/为 null/undefined 返回 null', () => {
    expect(extractCreatedTaskId({})).toBeNull()
    expect(extractCreatedTaskId({ id: null })).toBeNull()
    expect(extractCreatedTaskId({ id: undefined })).toBeNull()
    expect(extractCreatedTaskId(null)).toBeNull()
    expect(extractCreatedTaskId(undefined)).toBeNull()
    expect(extractCreatedTaskId('bad')).toBeNull()
  })

  it('id 为 0/负数/浮点/字符串/数组返回 null（契约要求正整数）', () => {
    expect(extractCreatedTaskId({ id: 0 })).toBeNull()
    expect(extractCreatedTaskId({ id: -5 })).toBeNull()
    expect(extractCreatedTaskId({ id: 1.5 })).toBeNull()
    expect(extractCreatedTaskId({ id: '101' })).toBeNull()
    expect(extractCreatedTaskId({ id: [101] })).toBeNull()
  })

  it('legacy task_id 字段不再被读取（契约形状为 id）', () => {
    expect(extractCreatedTaskId({ task_id: 101, plan: {} })).toBeNull()
  })
})

describe('buildPlanPreview：详情 → 预览数据', () => {
  it('plan 完整时输出归一化预览', () => {
    const preview = buildPlanPreview({
      id: 101,
      device_serial: 'A133P-01',
      plan: {
        intent: 'DDR 稳定性测试',
        selected_modules: ['DDR', '稳定性'],
        test_type: 'stability',
        item_ids: [12, 13]
      }
    })
    expect(preview).toEqual({
      task_id: 101,
      device_serial: 'A133P-01',
      hasPlan: true,
      plan: {
        intent: 'DDR 稳定性测试',
        selected_modules: ['DDR', '稳定性'],
        test_type: 'stability',
        item_ids: [12, 13],
        llmUsed: false
      }
    })
  })

  it('plan.llm_used 标注：true→AI 规划，false/缺失→规则规划', () => {
    expect(buildPlanPreview({ id: 1, plan: { llm_used: true } }).plan.llmUsed).toBe(true)
    expect(buildPlanPreview({ id: 1, plan: { llm_used: false } }).plan.llmUsed).toBe(false)
    expect(buildPlanPreview({ id: 1, plan: {} }).plan.llmUsed).toBe(false)
  })

  it('plan 为 null/缺失 → hasPlan=false（显示「该任务无规划快照」）', () => {
    expect(NO_PLAN_TEXT).toBe('该任务无规划快照')
    expect(buildPlanPreview({ id: 101, device_serial: 'A133P-01', plan: null })).toMatchObject({
      hasPlan: false,
      plan: null,
      device_serial: 'A133P-01'
    })
    expect(buildPlanPreview({ id: 101, device_serial: 'A133P-01' })).toMatchObject({ hasPlan: false, plan: null })
  })

  it('plan 部分缺失 → 字段兜底，不抛 TypeError', () => {
    const preview = buildPlanPreview({ id: 7, device_serial: 'rk1', plan: { intent: null } })
    expect(preview.hasPlan).toBe(true)
    expect(preview.plan).toEqual({ intent: '-', selected_modules: [], test_type: '-', item_ids: [], llmUsed: false })
  })

  it('device_serial 缺失时回退 device.serial_number，再兜底为 -', () => {
    expect(buildPlanPreview({ id: 9, device: { serial_number: 'rk3568-01' }, plan: null }).device_serial).toBe('rk3568-01')
    expect(buildPlanPreview({ id: 9, device: { serial_number: '' }, plan: null }).device_serial).toBe('-')
    expect(buildPlanPreview({ id: 9, plan: null }).device_serial).toBe('-')
  })

  it('入参为空/非对象返回 null（视图不渲染面板）', () => {
    expect(buildPlanPreview(null)).toBeNull()
    expect(buildPlanPreview(undefined)).toBeNull()
    expect(buildPlanPreview('bad')).toBeNull()
    expect(buildPlanPreview([1, 2])).toBeNull()
  })
})
