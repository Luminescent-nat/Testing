import request from '@/utils/request'

// 登录
export const login = (data) => {
  return request.post('/auth/login', data)
}

// 注册
export const register = (data) => {
  return request.post('/auth/register', data)
}

// 获取用户信息
export const getUserInfo = () => {
  return request.get('/auth/me')
}

// 获取设备列表
export const getDevices = (params) => {
  return request.get('/devices', { params })
}

// 刷新设备
export const refreshDevices = () => {
  return request.post('/devices/refresh')
}

// 获取测试模块
export const getModules = (params) => {
  return request.get('/modules', { params })
}

// 获取模块详情（包含测试项）
export const getModuleDetail = (moduleId) => {
  return request.get(`/modules/${moduleId}?include_items=true`)
}

// 创建测试模块
export const createModule = (data) => {
  return request.post('/modules', data)
}

// 更新测试模块
export const updateModule = (moduleId, data) => {
  return request.put(`/modules/${moduleId}`, data)
}

// 删除测试模块
export const deleteModule = (moduleId) => {
  return request.delete(`/modules/${moduleId}`)
}

// 获取任务列表
export const getTasks = (params) => {
  return request.get('/tasks', { params })
}

// 创建任务
export const createTask = (data) => {
  return request.post('/tasks', data)
}

// 获取任务详情
export const getTaskDetail = (id) => {
  return request.get(`/tasks/${id}`)
}

// 获取任务记录
export const getTaskRecords = (id) => {
  return request.get(`/tasks/${id}/records`)
}

// 取消任务
export const cancelTask = (id) => {
  return request.post(`/tasks/${id}/cancel`)
}

// 重跑失败项
export const rerunFailedTasks = (id) => {
  return request.post(`/tasks/${id}/rerun-failed`)
}

// 获取报告
export const getReport = (taskId) => {
  return request.get(`/reports/${taskId}`)
}
