/**
 * V1-06 前端统一统计展示工具（纯函数，可单测）。
 *
 * 口径来源：docs/contracts/reporting-v1.0.md、docs/design/execution-state-machine.md。
 * 关键约束：
 *  - 通过率必须使用后端 `pass_rate`（number|null），前端不得用 passed/total 自算；
 *  - `pass_rate === null` 表示无有效结果（全 skip / 零分母），显示“无有效结果”而非 0%/100%；
 *  - 计数 `0` 必须原样保留，不得显示为缺失；耗时 `0` 亦不视为缺失；
 *  - 报告对比以稳定 `item_id` 为键，`item_name` 仅显示，重名不同 ID 不得互换。
 *
 * @module utils/stats
 */

/** 五类终态（顺序固定） @type {string[]} */
export const FINAL_STATUSES = ['pass', 'fail', 'skip', 'error', 'timeout']

/**
 * 统计一组结果记录的五类状态计数（只统计终态，running/pending/未知忽略）。
 * @param {Array<{status?: string}>} [results] 结果记录数组
 * @returns {{pass: number, fail: number, skip: number, error: number, timeout: number}} 五类计数
 */
export const countStatuses = (results = []) => {
  const counts = { pass: 0, fail: 0, skip: 0, error: 0, timeout: 0 }
  for (const record of results || []) {
    const status = record?.status
    if (status in counts) counts[status] += 1
  }
  return counts
}

/**
 * 将后端 pass_rate（number|null|undefined）规范为 number|null；保留 0。
 * @param {number|string|null|undefined} value 原始值
 * @returns {number|null} 规范化通过率
 */
export const toPassRate = (value) => {
  if (value === null || value === undefined || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

/**
 * 格式化通过率显示：null → “无有效结果”，0 → “0%”，100 → “100%”。
 * @param {number|string|null|undefined} value 通过率
 * @returns {string} 展示文本
 */
export const formatPassRate = (value) => {
  const rate = toPassRate(value)
  return rate === null ? '无有效结果' : `${rate}%`
}

/**
 * 格式化耗时（秒）：null/undefined → “—”，0 → “0秒”，其余带秒。
 * @param {number|null|undefined} seconds 秒数
 * @returns {string} 展示文本
 */
export const formatDurationSeconds = (seconds) => {
  if (seconds === null || seconds === undefined || seconds === '') return '—'
  const total = Math.max(0, Math.floor(Number(seconds)))
  if (!Number.isFinite(total)) return '—'
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) return `${hours}小时${minutes}分${secs}秒`
  if (minutes > 0) return `${minutes}分${secs}秒`
  return `${secs}秒`
}

/**
 * 归一化报告/任务 summary：优先 counts 五类计数，其次契约 pass/fail/skip/error/timeout，
 * 最后兼容旧 passed/failed/skipped 键；pass_rate 保持后端 number|null。
 * @param {object} [summary] 后端 summary 或任务项
 * @returns {{totalItems: number, counts: {pass:number,fail:number,skip:number,error:number,timeout:number}, passRate: number|null}} 归一化结果
 */
export const normalizeSummary = (summary = {}) => {
  const source = summary || {}
  const rawCounts = source.counts && typeof source.counts === 'object' ? source.counts : null
  const counts = rawCounts
    ? {
        pass: Number(rawCounts.pass ?? 0),
        fail: Number(rawCounts.fail ?? 0),
        skip: Number(rawCounts.skip ?? 0),
        error: Number(rawCounts.error ?? 0),
        timeout: Number(rawCounts.timeout ?? 0)
      }
    : {
        pass: Number(source.pass ?? source.passed ?? 0),
        fail: Number(source.fail ?? source.failed ?? 0),
        skip: Number(source.skip ?? source.skipped ?? 0),
        error: Number(source.error ?? 0),
        timeout: Number(source.timeout ?? 0)
      }
  return {
    totalItems: Number(source.total_items ?? source.totalItems ?? 0),
    counts,
    passRate: toPassRate(source.pass_rate)
  }
}

/**
 * 由后端任务项与结果记录构造报告卡片 summary。
 * 通过率严格取后端 `task.pass_rate`（number|null），计数为结果状态精确汇总（不做通过率自算）。
 * @param {object} task 后端 tasks 项（含 pass_rate/total_items）
 * @param {Array<object>} [results] 该任务的结果记录
 * @returns {{totalItems: number, counts: object, passRate: number|null}} 卡片 summary
 */
export const deriveTaskSummary = (task = {}, results = []) => ({
  totalItems: Number(task?.total_items ?? 0),
  counts: countStatuses(results),
  passRate: toPassRate(task?.pass_rate)
})

/**
 * 归一化仪表盘统计：优先使用后端 `task_outcomes` 完整分列，回退 `today` 同名字段。
 * 明确不使用 `completed` 充当 `passed`（无 passed 字段时 passed 归 0）。
 * @param {object} [data] /dashboard/stats 的 data
 * @returns {{tasks:number, passed:number, failed:number, noResult:number, executionFailed:number, cancelled:number, running:number, pending:number, passRate:number|null, onlineDevices:number}} 分列统计
 */
export const normalizeDashboardOutcomes = (data = {}) => {
  const today = data?.today || {}
  const outcomes = data?.task_outcomes || {}
  const pick = (key, outcomeKey = key) =>
    Number(outcomes?.[outcomeKey] ?? today?.[key] ?? 0)
  return {
    tasks: Number(today.tasks ?? 0),
    passed: pick('passed'),
    failed: pick('failed'),
    noResult: pick('no_result'),
    executionFailed: pick('execution_failed'),
    cancelled: pick('cancelled'),
    running: pick('running'),
    pending: pick('pending'),
    passRate: toPassRate(today.pass_rate),
    onlineDevices: Number(data?.devices?.online ?? 0)
  }
}

/**
 * 构建报告对比行：以 `item_id` 为稳定键对齐，`item_name` 仅用于显示。
 * - 两侧同 item_id：comparable=true，按 status 判 same；
 * - 仅一侧存在：comparable=false，verdict=`not_comparable`（显示“不可对比”）；
 * - 耗时 0 原样保留（left_time/right_time 可为 0），缺失为 null。
 * @param {object} left 报告 A（含 results）
 * @param {object} right 报告 B（含 results）
 * @returns {{left: object, right: object, rows: Array<object>}} 对比结果
 */
export const buildCompareRows = (left = {}, right = {}) => {
  const rightMap = new Map((right.results || []).map((item) => [item.item_id, item]))
  const rows = (left.results || []).map((leftItem) => {
    const rightItem = rightMap.get(leftItem.item_id)
    rightMap.delete(leftItem.item_id)
    const comparable = !!rightItem
    return {
      item_id: leftItem.item_id,
      item_name: leftItem.item_name,
      module_name: leftItem.module_name,
      left_status: leftItem.status ?? null,
      left_time: leftItem.execution_time ?? null,
      right_status: comparable ? rightItem.status ?? null : null,
      right_time: comparable ? rightItem.execution_time ?? null : null,
      comparable,
      same: comparable && leftItem.status === rightItem.status,
      only_left: !comparable,
      only_right: false,
      verdict: !comparable ? 'not_comparable' : leftItem.status === rightItem.status ? 'same' : 'different'
    }
  })
  for (const rightItem of rightMap.values()) {
    rows.push({
      item_id: rightItem.item_id,
      item_name: rightItem.item_name,
      module_name: rightItem.module_name,
      left_status: null,
      left_time: null,
      right_status: rightItem.status ?? null,
      right_time: rightItem.execution_time ?? null,
      comparable: false,
      same: false,
      only_left: false,
      only_right: true,
      verdict: 'not_comparable'
    })
  }
  return { left, right, rows }
}
