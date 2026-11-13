/**
 * AI 自然语言创建任务的前端纯函数工具（RR-V11-REVIEW §2 修复，task-28）。
 *
 * 契约事实：
 *  - `POST /ai/tasks/natural` 返回 201 + 契约 Task 对象（`data.id` 为正整数），
 *    旧形状 `data={task_id, plan, device_serial}` 为 legacy 偏差，已废弃；
 *  - 规划快照在 `GET /tasks/{id}` 的 `TestTaskDetail.plan`（object|null），
 *    `plan` 内含 `intent / selected_modules / test_type / item_ids`。
 *
 * 本模块只做纯转换，视图仅调用这些函数 + 可选链守卫，避免渲染期 TypeError。
 *
 * @module utils/aiTask
 */

/** plan 为 null/缺失时的展示文案 @type {string} */
export const NO_PLAN_TEXT = '该任务无规划快照'

/**
 * 从创建响应 data 中提取合法任务 ID（正整数 number）。
 * 契约 `id` 为 integer；缺失、0、负数、浮点、字符串、非对象一律返回 null。
 * @param {unknown} data 创建响应的 data（契约 Task 对象）
 * @returns {number|null} 合法任务 ID 或 null
 */
export const extractCreatedTaskId = (data) => {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return null
  const raw = data.id
  if (typeof raw !== 'number' || !Number.isInteger(raw) || raw <= 0) return null
  return raw
}

/**
 * 由任务详情（或创建响应兜底）构造预览面板数据。
 * - `plan` 为 null/缺失/非对象 → `hasPlan=false`（视图显示「该任务无规划快照」）；
 * - `plan` 部分字段缺失 → 用空数组/'-' 兜底，不抛 TypeError；
 * - `device_serial` 兜底顺序：`detail.device_serial` → `detail.device.serial_number` → '-'。
 * @param {object|null|undefined} detail 任务详情（TestTaskDetail）或创建响应 data
 * @returns {{task_id: number|null, device_serial: string, hasPlan: boolean, plan: {intent: string, selected_modules: string[], test_type: string, item_ids: number[]}|null}|null} 预览数据；入参为空时返回 null
 */
export const buildPlanPreview = (detail) => {
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return null
  const rawPlan = detail.plan
  const hasPlan = !!rawPlan && typeof rawPlan === 'object' && !Array.isArray(rawPlan)
  const deviceSerial =
    typeof detail.device_serial === 'string' && detail.device_serial !== ''
      ? detail.device_serial
      : typeof detail.device?.serial_number === 'string' && detail.device.serial_number !== ''
        ? detail.device.serial_number
        : '-'
  return {
    task_id: extractCreatedTaskId(detail),
    device_serial: deviceSerial,
    hasPlan,
    plan: hasPlan
      ? {
          intent: typeof rawPlan.intent === 'string' && rawPlan.intent !== '' ? rawPlan.intent : '-',
          selected_modules: Array.isArray(rawPlan.selected_modules) ? rawPlan.selected_modules : [],
          test_type: typeof rawPlan.test_type === 'string' && rawPlan.test_type !== '' ? rawPlan.test_type : '-',
          item_ids: Array.isArray(rawPlan.item_ids) ? rawPlan.item_ids : []
        }
      : null
  }
}
