import request from '@/utils/request'

// 获取单任务报告
export const getReport = (taskId) => {
  return request.get(`/reports/${taskId}`)
}

// 导出单任务报告
export const exportReport = (taskId, format = 'html') => {
  return request.get(`/reports/${taskId}/export`, {
    params: { format },
    responseType: 'blob'
  })
}

// 获取全部任务总报告
export const getSummaryReport = () => {
  return request.get('/reports/summary/all')
}

// 批量导出报告
export const exportBatchReport = (taskIds, format = 'html') => {
  return request.get('/reports/batch/export', {
    params: { task_ids: taskIds.join(','), format },
    responseType: 'blob'
  })
}

// 获取测试项详细日志
export const getItemLog = (taskId, itemId) => {
  return request.get(`/reports/${taskId}/items/${itemId}/log`)
}

// 最近 N 天任务趋势统计
export const getStatsTrend = (days = 30) => {
  return request.get('/reports/stats/trend', { params: { days } })
}

// 各测试模块通过率统计
export const getStatsByModule = () => {
  return request.get('/reports/stats/by-module')
}
