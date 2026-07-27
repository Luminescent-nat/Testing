import request from '@/utils/request'

// 仪表盘头部统计卡片（今日任务/通过率/失败数/运行中/设备）
export const getDashboardStats = () => {
  return request.get('/dashboard/stats')
}
