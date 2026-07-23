import request from '@/utils/request'

// 查询失败模式库
export const getFailurePatterns = (params = {}) => {
  return request.get('/memory/failure-patterns', { params })
}

// 创建失败模式
export const createFailurePattern = (data) => {
  return request.post('/memory/failure-patterns', data)
}

// 更新失败模式
export const updateFailurePattern = (id, data) => {
  return request.put(`/memory/failure-patterns/${id}`, data)
}

// 删除失败模式
export const deleteFailurePattern = (id) => {
  return request.delete(`/memory/failure-patterns/${id}`)
}

// 查询统计基线
export const getBaselines = (params = {}) => {
  return request.get('/memory/baselines', { params })
}

// 创建统计基线
export const createBaseline = (data) => {
  return request.post('/memory/baselines', data)
}

// 更新统计基线
export const updateBaseline = (id, data) => {
  return request.put(`/memory/baselines/${id}`, data)
}

// 删除统计基线
export const deleteBaseline = (id) => {
  return request.delete(`/memory/baselines/${id}`)
}

// 查询黄金案例库
export const getGoldenCases = (params = {}) => {
  return request.get('/memory/golden-cases', { params })
}

// 创建黄金案例
export const createGoldenCase = (data) => {
  return request.post('/memory/golden-cases', data)
}

// 更新黄金案例
export const updateGoldenCase = (id, data) => {
  return request.put(`/memory/golden-cases/${id}`, data)
}

// 删除黄金案例
export const deleteGoldenCase = (id) => {
  return request.delete(`/memory/golden-cases/${id}`)
}
