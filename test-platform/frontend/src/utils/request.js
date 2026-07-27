import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'

// 后端技术错误 → 用户友好提示映射
const FRIENDLY_ERROR_MAP = {
  '设备离线': '未检测到设备，请检查 USB 连接并重新刷新设备列表。',
  '设备不存在': '未找到目标设备，请检查设备是否已连接或已被移除。',
  '设备正在执行其他任务': '该设备当前正在执行其他测试任务，请等待完成后再试。',
  '测试项不存在': '选中的测试项已不存在，请刷新测试模块列表后重试。',
  '任务不存在': '未找到该任务，可能已被删除。',
  '无权限查看此任务': '您没有权限查看该任务。',
  '无权限取消此任务': '您没有权限取消该任务。',
  '无权限查看报告': '您没有权限查看该报告。',
  '输入文本不能为空': '请输入测试指令后再提交。',
  '无法从输入中识别目标设备或测试意图': '未能识别设备或测试意图，请尝试描述具体设备型号和测试模块。',
  '未找到匹配的测试项': '当前没有匹配的测试项，请检查测试模块配置或更换描述。',
  '任务无法取消': '当前任务状态不允许取消。',
  '用户名或密码错误': '用户名或密码错误，请重新输入。',
  '用户名已存在': '该用户名已被注册，请更换用户名。',
  '用户不存在': '用户不存在。',
  '无效的认证凭据': '登录信息已失效，请重新登录。',
  '需要管理员权限': '需要管理员权限才能执行此操作。',
  '未找到可汇总的任务报告': '没有可汇总的任务报告。',
  'PDF 导出待后续实现': 'PDF 导出功能暂未实现，请选择其他格式。'
}

// 将后端 detail/message 转换为用户友好提示
const getFriendlyError = (rawMessage) => {
  if (!rawMessage) return null
  // 优先精确匹配
  if (FRIENDLY_ERROR_MAP[rawMessage]) {
    return FRIENDLY_ERROR_MAP[rawMessage]
  }
  // 正则/关键字匹配一些动态错误
  if (/命令包含未替换的占位符/.test(rawMessage)) {
    return '测试项命令中的占位符未找到对应设备参数，请检查测试项配置。'
  }
  if (/兼容性不满足|架构不兼容|设备缺少必要能力|主板平台不兼容|硬件名称不兼容|Android版本/.test(rawMessage)) {
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

// 客户端 PC 唯一标识：首次访问生成 UUID 持久化，所有请求通过
// X-PC-Identifier 上报，后端据此做设备归属隔离（普通用户只见本机设备）。
const PC_IDENTIFIER_KEY = 'pc_identifier'
export const getPcIdentifier = () => {
  let id = localStorage.getItem(PC_IDENTIFIER_KEY)
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) ||
      `pc-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
    localStorage.setItem(PC_IDENTIFIER_KEY, id)
  }
  return id
}

// 创建axios实例
const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    config.headers['X-PC-Identifier'] = getPcIdentifier()
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    // blob / arraybuffer 响应直接返回，不执行 code 校验
    if (response.config.responseType === 'blob' || response.config.responseType === 'arraybuffer') {
      return response.data
    }
    const res = response.data
    if (res.code !== 200) {
      const msg = getFriendlyError(res.message) || res.message || '请求失败'
      ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }
    return res
  },
  (error) => {
    const { response } = error
    if (response?.status === 401) {
      const userStore = useUserStore()
      userStore.logout()
      ElMessage.error('登录已过期，请重新登录')
    } else if (response?.status === 422) {
      const detail = response.data?.detail
      let msg = '请求参数错误'
      if (Array.isArray(detail) && detail.length > 0) {
        msg = detail.map(item => `${item.loc?.slice(-1)?.[0] || '字段'}: ${item.msg}`).join('；')
      } else if (typeof detail === 'string') {
        msg = getFriendlyError(detail) || detail
      }
      ElMessage.error(msg)
    } else {
      const rawMessage = response?.data?.message || response?.data?.detail || error.message
      ElMessage.error(getFriendlyError(rawMessage) || rawMessage || '网络错误')
    }
    return Promise.reject(error)
  }
)

export default request
