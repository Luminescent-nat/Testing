/**
 * 统一契约 API 客户端（依据 docs/contracts/README.md v1.0）
 *
 * 职责：
 *  - 统一 REST 根路径 `/api/v1`；
 *  - 注入 `Authorization: Bearer <JWT>` 与 `X-PC-Identifier`；
 *  - 同时兼容新契约错误外层 `{ code: string, message, details }` 与
 *    legacy `{ detail }` / `{ errors }` / `{ code: number }` 结构；
 *  - 任务创建/重跑（POST）自动附加 `Idempotency-Key`，支持调用方显式传入，
 *    缺省生成 8～128 位可打印 ASCII；
 *  - 成功响应保留完整外层 `{ code, message, data }`，且 `data` 中的
 *    `0` / `false` / `""` / `null` 不会被丢弃；
 *  - 401 触发登出。
 *
 * 该模块取代 src/utils/request.js 中的重复实现；request.js 仅做委托，
 * 以保持现有 api/*.js 调用方与响应结构完全兼容（视图层无需改动）。
 *
 * @module api/client
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'

/** REST 根路径 @type {string} */
export const API_BASE_URL = '/api/v1'

/** 幂等键请求头名称 @type {string} */
export const IDEMPOTENCY_HEADER = 'Idempotency-Key'

/** 幂等键最小长度 @type {number} */
export const IDEMPOTENCY_KEY_MIN_LENGTH = 8

/** 幂等键最大长度 @type {number} */
export const IDEMPOTENCY_KEY_MAX_LENGTH = 128

/** PC 标识持久化键 @type {string} */
export const PC_IDENTIFIER_KEY = 'pc_identifier'

/**
 * 可打印 ASCII（0x20～0x7E）正则，用于校验调用方传入的幂等键。
 * @type {RegExp}
 */
export const PRINTABLE_ASCII_RE = /^[\x20-\x7e]+$/

/**
 * 后端技术错误 → 用户友好提示映射（沿用既有行为）。
 * @type {Record<string, string>}
 */
const FRIENDLY_ERROR_MAP = {
  设备离线: '未检测到设备，请检查 USB 连接并重新刷新设备列表。',
  设备不存在: '未找到目标设备，请检查设备是否已连接或已被移除。',
  设备正在执行其他任务: '该设备当前正在执行其他测试任务，请等待完成后再试。',
  测试项不存在: '选中的测试项已不存在，请刷新测试模块列表后重试。',
  任务不存在: '未找到该任务，可能已被删除。',
  无权限查看此任务: '您没有权限查看该任务。',
  无权限取消此任务: '您没有权限取消该任务。',
  无权限查看报告: '您没有权限查看该报告。',
  输入文本不能为空: '请输入测试指令后再提交。',
  无法从输入中识别目标设备或测试意图: '未能识别设备或测试意图，请尝试描述具体设备型号和测试模块。',
  未找到匹配的测试项: '当前没有匹配的测试项，请检查测试模块配置或更换描述。',
  任务无法取消: '当前任务状态不允许取消。',
  用户名或密码错误: '用户名或密码错误，请重新输入。',
  用户名已存在: '该用户名已被注册，请更换用户名。',
  用户不存在: '用户不存在。',
  无效的认证凭据: '登录信息已失效，请重新登录。',
  需要管理员权限: '需要管理员权限才能执行此操作。',
  未找到可汇总的任务报告: '没有可汇总的任务报告。',
  'PDF 导出待后续实现': 'PDF 导出功能暂未实现，请选择其他格式。'
}

/**
 * 将后端 detail/message 转换为用户友好提示。
 * @param {string|null|undefined} rawMessage 原始错误摘要
 * @returns {string|null} 友好提示，无匹配时返回原值
 */
export const getFriendlyError = (rawMessage) => {
  if (!rawMessage) return null
  if (FRIENDLY_ERROR_MAP[rawMessage]) {
    return FRIENDLY_ERROR_MAP[rawMessage]
  }
  if (/命令包含未替换的占位符/.test(rawMessage)) {
    return '测试项命令中的占位符未找到对应设备参数，请检查测试项配置。'
  }
  if (
    /兼容性不满足|架构不兼容|设备缺少必要能力|主板平台不兼容|硬件名称不兼容|Android版本/.test(rawMessage)
  ) {
    return '该测试项不支持当前设备的 Android 版本 / CPU 架构 / 能力特征，已自动跳过。'
  }
  if (/device.*not found|no devices\/emulators found/i.test(rawMessage)) {
    return 'ADB 未找到目标设备，请检查 USB 连接和调试授权。'
  }
  if (/device.*offline/i.test(rawMessage)) {
    return '设备处于 offline 状态，请重新授权 USB 调试或重启 ADB 服务。'
  }
  if (/permission denied|operation not permitted/i.test(rawMessage)) {
    return '设备端命令权限不足，请确认是否已 root 或调整执行路径。'
  }
  if (/no such file or directory/i.test(rawMessage)) {
    return '目标文件不存在，请检查工具推送是否成功或工具架构是否匹配。'
  }
  if (/timeout|timed out/i.test(rawMessage)) {
    return '命令执行超时，请增大测试项超时时间或检查设备是否卡死。'
  }
  return rawMessage
}

/**
 * 客户端 PC 唯一标识：首次访问生成并持久化，所有请求通过
 * X-PC-Identifier 上报，后端据此做设备归属隔离。
 * @returns {string} PC 标识
 */
export const getPcIdentifier = () => {
  let id = localStorage.getItem(PC_IDENTIFIER_KEY)
  if (!id) {
    id =
      (typeof crypto !== 'undefined' && crypto.randomUUID && crypto.randomUUID()) ||
      `pc-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
    localStorage.setItem(PC_IDENTIFIER_KEY, id)
  }
  return id
}

/**
 * 将 PC 标识并入请求体（登录/注册等契约要求 `pc_identifier` 的接口使用）。
 * @param {object} [payload] 原请求体
 * @returns {object} 附加 pc_identifier 后的新对象（不改入参）
 */
export const withPcIdentifier = (payload = {}) => ({ ...payload, pc_identifier: getPcIdentifier() })

/**
 * 重复提交保护（纯逻辑，可与视图的按钮 `:disabled`/`:loading` 配合）：
 * 上一次未完成时跳过后续调用，返回 undefined，不重复发起请求。
 * @returns {{ isPending: () => boolean, run: (fn: () => unknown) => Promise<unknown> }} guard 对象
 */
export const createSubmitGuard = () => {
  let pending = false
  return {
    isPending: () => pending,
    run: async (fn) => {
      if (pending) return undefined
      pending = true
      try {
        return await fn()
      } finally {
        pending = false
      }
    }
  }
}

/**
 * 判断给定字符串是否为合法幂等键（8～128 位可打印 ASCII）。
 * @param {unknown} key 待校验值
 * @returns {boolean} 是否合法
 */
export const isValidIdempotencyKey = (key) =>
  typeof key === 'string' &&
  key.length >= IDEMPOTENCY_KEY_MIN_LENGTH &&
  key.length <= IDEMPOTENCY_KEY_MAX_LENGTH &&
  PRINTABLE_ASCII_RE.test(key)

/**
 * 生成确定性范围内的随机幂等键（32 位十六进制，可打印 ASCII）。
 * @returns {string} 幂等键
 */
export const generateIdempotencyKey = () => {
  const uuid =
    (typeof crypto !== 'undefined' && crypto.randomUUID && crypto.randomUUID()) ||
    `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`
  const cleaned = uuid.replace(/-/g, '')
  if (cleaned.length >= IDEMPOTENCY_KEY_MIN_LENGTH) {
    return cleaned.slice(0, 32)
  }
  return `${cleaned}${'0'.repeat(IDEMPOTENCY_KEY_MIN_LENGTH)}`.slice(0, 32)
}

/**
 * 需要幂等键的 POST 任务创建/重跑路径（含 legacy 别名）。
 * 依据契约：任务创建、失败重跑必须携带 Idempotency-Key；其他写接口不用。
 * @type {RegExp[]}
 */
const IDEMPOTENT_POST_PATTERNS = [
  /^\/tasks$/, // POST /api/v1/tasks 任务创建
  /^\/tasks\/[^/]+\/reruns$/, // POST /api/v1/tasks/{id}/reruns 失败重跑
  /^\/tasks\/[^/]+\/rerun-failed$/, // legacy 失败重跑路径
  /^\/ai\/tasks\/natural$/ // legacy 自然语言创建任务
]

/**
 * 去掉查询串并补全前导斜杠，得到用于匹配的路径。
 * @param {string|undefined} url 请求 URL
 * @returns {string} 归一化路径
 */
const normalizePath = (url) => {
  if (!url) return ''
  let noQuery = String(url).split('?')[0]
  if (noQuery.startsWith(`${API_BASE_URL}/`)) {
    noQuery = noQuery.slice(API_BASE_URL.length)
  } else if (noQuery === API_BASE_URL) {
    noQuery = '/'
  }
  return noQuery.startsWith('/') ? noQuery : `/${noQuery}`
}

/**
 * 判断该请求是否属于“任务创建/重跑”等需要幂等键的写操作。
 * @param {object} config axios 请求配置
 * @param {string} [config.method] 方法
 * @param {string} [config.url] 路径
 * @returns {boolean} 是否需要幂等键
 */
export const shouldAttachIdempotencyKey = (config = {}) => {
  const method = String(config.method || 'get').toUpperCase()
  if (method !== 'POST') return false
  const path = normalizePath(config.url)
  return IDEMPOTENT_POST_PATTERNS.some((re) => re.test(path))
}

/**
 * 解析并（必要时）生成该请求的幂等键。
 * 规则：
 *  - 调用方显式传入（config.idempotencyKey 或已有 Idempotency-Key 头）时优先使用并校验；
 *  - 否则仅对任务创建/重跑类 POST 自动生成；
 *  - 其他请求返回 null（不加头）。
 * @param {object} config axios 请求配置
 * @returns {string|null} 幂等键
 * @throws {ApiError} 调用方传入的键不合法（长度/字符集）
 */
export const resolveIdempotencyKey = (config = {}) => {
  const headers = config.headers || {}
  const provided =
    config.idempotencyKey !== undefined && config.idempotencyKey !== null
      ? config.idempotencyKey
      : headers[IDEMPOTENCY_HEADER] !== undefined
        ? headers[IDEMPOTENCY_HEADER]
        : headers[IDEMPOTENCY_HEADER.toLowerCase()]

  if (provided !== undefined && provided !== null) {
    const key = String(provided)
    if (!isValidIdempotencyKey(key)) {
      throw new ApiError({
        code: 'CLIENT_INVALID_IDEMPOTENCY_KEY',
        message: `Idempotency-Key 非法：必须为 ${IDEMPOTENCY_KEY_MIN_LENGTH}～${IDEMPOTENCY_KEY_MAX_LENGTH} 位可打印 ASCII`,
        details: { field: 'Idempotency-Key' },
        httpStatus: null
      })
    }
    return key
  }

  if (!shouldAttachIdempotencyKey(config)) return null
  return generateIdempotencyKey()
}

/**
 * 归一化错误详情。
 * @typedef {object} NormalizedError
 * @property {string|null} code 机器码（新契约字符串码或由 HTTP 映射）
 * @property {string|null} rawMessage 原始摘要（未做友好映射）
 * @property {object} details 定位信息
 * @property {number|null} httpStatus HTTP 状态码
 * @property {boolean} legacy 是否来自 legacy 结构
 */

const HTTP_CODE_MAP = {
  400: 'VALIDATION_ERROR',
  401: 'UNAUTHENTICATED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  409: 'CONFLICT',
  422: 'VALIDATION_ERROR',
  500: 'INTERNAL_ERROR',
  503: 'SERVICE_UNAVAILABLE'
}

/**
 * 将 HTTP 状态码映射到契约错误码。
 * @param {number|undefined|null} status HTTP 状态码
 * @returns {string|null} 契约错误码
 */
export const mapHttpStatusToCode = (status) => (status ? HTTP_CODE_MAP[status] || null : null)

/**
 * 格式化 legacy DRF 风格 detail 数组（如 [{ loc, msg }]）。
 * @param {Array<unknown>} detailArr detail 数组
 * @returns {string} 拼接摘要
 */
const formatLegacyDetailArray = (detailArr) =>
  detailArr
    .map((item) => {
      if (item && typeof item === 'object') {
        const field = Array.isArray(item.loc) ? item.loc.slice(-1)[0] : item.field
        const msg = item.msg || item.message || item.detail || ''
        return field ? `${field}: ${msg}` : String(msg)
      }
      return String(item)
    })
    .filter(Boolean)
    .join('；')

/**
 * 归一化 legacy `errors` 字段为 details 对象。
 * @param {unknown} errors errors 字段
 * @returns {object} details 对象
 */
const normalizeLegacyErrors = (errors) => {
  if (Array.isArray(errors)) {
    return { errors }
  }
  if (errors && typeof errors === 'object') {
    return { errors }
  }
  return { reason: String(errors) }
}

/**
 * 将任意错误外层（新契约或 legacy）归一化为统一结构。
 * @param {unknown} payload 响应体（错误外层）
 * @param {number|null} [httpStatus] HTTP 状态码
 * @returns {NormalizedError} 归一化错误
 */
export const normalizeErrorPayload = (payload, httpStatus = null) => {
  const result = {
    code: null,
    rawMessage: null,
    details: {},
    httpStatus: httpStatus ?? null,
    legacy: false
  }
  if (!payload || typeof payload !== 'object') {
    result.code = mapHttpStatusToCode(httpStatus)
    return result
  }

  const body = /** @type {Record<string, unknown>} */ (payload)

  if (typeof body.code === 'string' && body.code) {
    result.code = body.code
  } else if (typeof body.code === 'number') {
    result.code = mapHttpStatusToCode(body.code) || mapHttpStatusToCode(httpStatus)
    result.legacy = true
  } else {
    result.code = mapHttpStatusToCode(httpStatus)
  }

  if (typeof body.message === 'string' && body.message) {
    result.rawMessage = body.message
  }

  if (body.details && typeof body.details === 'object' && !Array.isArray(body.details)) {
    result.details = body.details
  } else if (body.errors !== undefined) {
    result.details = normalizeLegacyErrors(body.errors)
    result.legacy = true
  }

  if (Array.isArray(body.detail)) {
    result.rawMessage = result.rawMessage || formatLegacyDetailArray(body.detail)
    result.details = { ...result.details, errors: body.detail }
    result.legacy = true
  } else if (typeof body.detail === 'string' && body.detail) {
    result.rawMessage = result.rawMessage || body.detail
    result.legacy = true
  }

  if (!result.rawMessage && typeof body.error === 'string') {
    result.rawMessage = body.error
    result.legacy = true
  }

  return result
}

/**
 * 契约/网络错误对象，保留机器码、详情与 HTTP 状态，便于视图追溯。
 */
export class ApiError extends Error {
  /**
   * @param {object} params 构造参数
   * @param {string|null} [params.code] 机器码
   * @param {string} [params.message] 已本地化的用户可读摘要
   * @param {string|null} [params.rawMessage] 后端原始摘要
   * @param {object} [params.details] 定位信息
   * @param {number|null} [params.httpStatus] HTTP 状态码
   * @param {boolean} [params.legacy] 是否 legacy 结构
   * @param {{status: number|null, data: unknown}|null} [params.response] 兼容字段：
   *   供既有视图按 `error?.response?.status` 判断（与 axios 错误形状对齐）
   * @param {unknown} [params.cause] 原始异常
   */
  constructor({
    code = null,
    message = '',
    rawMessage = null,
    details = {},
    httpStatus = null,
    legacy = false,
    response = null,
    cause
  } = {}) {
    super(message || rawMessage || '请求失败')
    this.name = 'ApiError'
    this.code = code || null
    this.rawMessage = rawMessage || null
    this.details = details || {}
    this.httpStatus = httpStatus ?? null
    this.legacy = !!legacy
    this.response = response
    if (cause !== undefined) this.cause = cause
  }
}

/**
 * 将错误外层转换为带用户友好提示的 ApiError。
 * @param {unknown} payload 错误外层
 * @param {number|null} [httpStatus] HTTP 状态码
 * @param {unknown} [cause] 原始异常
 * @param {string} [fallbackMessage] 无内容时的兜底摘要
 * @param {{status: number|null, data: unknown}|null} [response] 兼容用的 response 快照
 * @returns {ApiError} 错误对象
 */
export const toApiError = (
  payload,
  httpStatus = null,
  cause,
  fallbackMessage = '请求失败',
  response = null
) => {
  const norm = normalizeErrorPayload(payload, httpStatus)
  const friendly = getFriendlyError(norm.rawMessage) || norm.rawMessage || fallbackMessage
  return new ApiError({
    code: norm.code,
    message: friendly,
    rawMessage: norm.rawMessage,
    details: norm.details,
    httpStatus: norm.httpStatus,
    legacy: norm.legacy,
    response,
    cause
  })
}

/**
 * 判断响应体是否为成功外层。
 * 新契约与 legacy 一致要求成功响应体为 `{ code: 整数(2xx), message, data }`；
 * 错误外层的 `code` 为字符串；HTTP 200 携带数字 `code>=400` 是 legacy 业务错误。
 * 注意：blob/arraybuffer 在响应拦截器中已提前返回，不会进入本判断；
 * 无 `code` 的裸响应体按旧实现语义视为异常（视图/存储层统一走 isSuccessResponse）。
 * @param {unknown} body 响应体
 * @returns {boolean} 是否成功
 */
export const isSuccessEnvelope = (body) => {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return false
  const code = /** @type {Record<string, unknown>} */ (body).code
  return typeof code === 'number' && code >= 200 && code < 300
}

/**
 * 统一成功判定（视图/存储层唯一入口，禁止散落 `code === 200`）：
 * 成功外层为 `{ code: 整数(2xx), message, data }`，200/201/204 均视为成功；
 * 错误外层 `code` 为字符串或非 2xx 整数，判为失败。
 * 该判定不影响 `data` 取值：`data` 中的 `0` / `false` / `""` / `null` 原样保留。
 * @param {unknown} body 响应外层
 * @returns {boolean} 是否为成功响应
 */
export const isSuccessResponse = (body) => isSuccessEnvelope(body)

/**
 * 兼容 AxiosHeaders 与普通对象的请求头写入。
 * @param {object} headers 请求头容器
 * @param {string} name 头名称
 * @param {string} value 头值
 * @returns {void}
 */
const setHeader = (headers, name, value) => {
  if (headers && typeof headers.set === 'function') {
    headers.set(name, value)
  } else if (headers) {
    headers[name] = value
  }
}

/**
 * 创建 axios 实例。
 * @type {import('axios').AxiosInstance}
 */
const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器：注入鉴权、PC 标识与幂等键
client.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    if (userStore.token) {
      setHeader(config.headers, 'Authorization', `Bearer ${userStore.token}`)
    }
    setHeader(config.headers, 'X-PC-Identifier', getPcIdentifier())

    try {
      const idempotencyKey = resolveIdempotencyKey(config)
      if (idempotencyKey) {
        setHeader(config.headers, IDEMPOTENCY_HEADER, idempotencyKey)
      }
    } catch (validationError) {
      return Promise.reject(validationError)
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器：解析成功/错误外层，保留完整 data（含 0/false/""/null）
client.interceptors.response.use(
  (response) => {
    const responseType = response.config?.responseType
    if (responseType === 'blob' || responseType === 'arraybuffer') {
      return response.data
    }
    const body = response.data
    if (!isSuccessEnvelope(body)) {
      const apiError = toApiError(
        body,
        response.status,
        undefined,
        '请求失败',
        { status: response.status, data: body }
      )
      ElMessage.error(apiError.message)
      return Promise.reject(apiError)
    }
    return body
  },
  (error) => {
    const response = error?.response
    const status = response?.status ?? null
    const apiError = toApiError(
      response?.data,
      status,
      error,
      error?.message || '网络错误',
      response ? { status: response.status, data: response.data } : null
    )
    if (status === 401) {
      const userStore = useUserStore()
      userStore.logout()
      ElMessage.error('登录已过期，请重新登录')
    } else {
      ElMessage.error(apiError.message || '网络错误')
    }
    return Promise.reject(apiError)
  }
)

export { client }
export default client
