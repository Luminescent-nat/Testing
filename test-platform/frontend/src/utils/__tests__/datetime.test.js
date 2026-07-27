import { describe, it, expect } from 'vitest'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import { formatDateTime } from '../datetime'

dayjs.extend(utc)

describe('formatDateTime', () => {
  it('空值返回占位符', () => {
    expect(formatDateTime(null)).toBe('-')
    expect(formatDateTime(undefined)).toBe('-')
    expect(formatDateTime('')).toBe('-')
  })

  it('UTC 时间转换为本时区并按默认格式输出', () => {
    const utcTime = '2024-01-15T08:30:00Z'
    const expected = dayjs.utc(utcTime).local().format('YYYY-MM-DD HH:mm:ss')
    expect(formatDateTime(utcTime)).toBe(expected)
    expect(formatDateTime(utcTime)).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
  })

  it('支持自定义格式', () => {
    const utcTime = '2024-01-15T08:30:00Z'
    const expected = dayjs.utc(utcTime).local().format('YYYY/MM/DD')
    expect(formatDateTime(utcTime, 'YYYY/MM/DD')).toBe(expected)
  })
})
