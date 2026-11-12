/**
 * 兼容层：委托 `@/api/client` 的统一契约实现。
 *
 * 说明（T-20）：
 *  - 真正的统一 /api/v1 客户端、错误外层解析、幂等键、401 登出等逻辑
 *    已迁移至 `src/api/client.js`；
 *  - 本模块仅为现有 `api/*.js` 调用方保留默认导出（axios 实例）与
 *    `getPcIdentifier` 命名导出，保持调用方式与响应结构完全不变；
 *  - 视图层与 api/*.js 无需任何改动。
 */
import client, { getPcIdentifier } from '@/api/client'

export { getPcIdentifier }
export default client
