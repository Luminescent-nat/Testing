import request from '@/utils/request'

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

// 取消任务
export const cancelTask = (id) => {
  return request.post(`/tasks/${id}/cancel`)
}

// 重跑失败项
export const rerunFailedTasks = (id) => {
  return request.post(`/tasks/${id}/rerun-failed`)
}

// 获取任务记录
export const getTaskRecords = (id) => {
  return request.get(`/tasks/${id}/records`)
}

// 下载测试记录完整日志（blob）
export const downloadRecordLog = (recordId) => {
  return request.get(`/records/${recordId}/log`, { responseType: 'blob' })
}
