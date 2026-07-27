import request from '@/utils/request'

// 获取测试模块列表
export const getModules = (params) => {
  return request.get('/modules', { params })
}

// 获取模块详情（includeItems 为 true 时附带测试项列表，即 ?include_items=true）
export const getModuleDetail = (id, includeItems = false) => {
  return request.get(`/modules/${id}`, {
    params: includeItems ? { include_items: true } : {}
  })
}

// 创建模块
export const createModule = (data) => {
  return request.post('/modules', data)
}

// 更新模块
export const updateModule = (id, data) => {
  return request.put(`/modules/${id}`, data)
}

// 删除模块
export const deleteModule = (id) => {
  return request.delete(`/modules/${id}`)
}

// 获取测试项列表
export const getModuleItems = (moduleId) => {
  return request.get(`/modules/${moduleId}/items`)
}

// 创建测试项
export const createItem = (moduleId, data) => {
  return request.post(`/modules/${moduleId}/items`, data)
}

// 更新测试项
export const updateItem = (moduleId, itemId, data) => {
  return request.put(`/modules/${moduleId}/items/${itemId}`, data)
}

// 删除测试项
export const deleteItem = (moduleId, itemId) => {
  return request.delete(`/modules/${moduleId}/items/${itemId}`)
}
