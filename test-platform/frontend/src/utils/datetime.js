import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'

dayjs.extend(utc)

/**
 * 将后端返回的 UTC 时间格式化为本地时间。
 * @param {string|Date|null} time
 * @param {string} pattern
 * @returns {string}
 */
export function formatDateTime(time, pattern = 'YYYY-MM-DD HH:mm:ss') {
  if (!time) return '-'
  return dayjs.utc(time).local().format(pattern)
}
