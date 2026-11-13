/**
 * 监控页测试记录名称归一化（演示前收口 task-29）。
 *
 * 契约事实：`TestRecord` 的名称字段是 `item_name`（不是 `item.name`）。
 * 监控页历史实现误用 `item.name`，导致实测时间线/详情出现 `DDR/undefined`。
 * 本模块提供纯函数，统一用 `item_name` 并以「未知测试项」兜底，避免任何路径出现 undefined。
 *
 * @module utils/monitorRecord
 */

/** 名称缺失时的兜底文案 @type {string} */
export const UNKNOWN_ITEM_NAME = '未知测试项'

/**
 * 归一化单条测试记录的名称字段。
 * - `item_name` 为非空字符串时原样保留；缺失/null/空串/纯空白 → 「未知测试项」；
 * - `module_name` 非空字符串保留，否则回退 `module.name`，再兜底空串；
 * - 其余字段原样透传，不修改入参。
 * @param {object|null|undefined} record 测试记录（TestRecord）
 * @returns {object} 归一化后的记录
 */
export const normalizeRecord = (record) => {
  const source = record && typeof record === 'object' && !Array.isArray(record) ? record : {}
  const rawName = source.item_name
  const itemName = typeof rawName === 'string' && rawName.trim() !== '' ? rawName : UNKNOWN_ITEM_NAME
  const rawModule = source.module_name
  const moduleName =
    typeof rawModule === 'string' && rawModule.trim() !== ''
      ? rawModule
      : typeof source.module?.name === 'string' && source.module.name.trim() !== ''
        ? source.module.name
        : ''
  return { ...source, item_name: itemName, module_name: moduleName }
}

/**
 * 批量归一化测试记录数组（非数组返回空数组）。
 * @param {Array<object>|null|undefined} records 测试记录集合
 * @returns {Array<object>} 归一化后的记录数组
 */
export const normalizeRecords = (records) => (Array.isArray(records) ? records.map(normalizeRecord) : [])

/**
 * 生成测试项展示标题「模块 / 测试项」，任一路径都不会出现 undefined。
 * @param {object|null|undefined} record 测试记录
 * @returns {string} 展示标题
 */
export const formatRecordTitle = (record) => {
  const normalized = normalizeRecord(record)
  return normalized.module_name ? `${normalized.module_name} / ${normalized.item_name}` : normalized.item_name
}
