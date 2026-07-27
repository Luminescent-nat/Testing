import request from '@/utils/request'

// 自然语言创建 AI 测试任务
export const createNaturalTask = (text) => {
  return request.post('/ai/tasks/natural', { text })
}
