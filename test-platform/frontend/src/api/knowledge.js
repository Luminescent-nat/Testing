import request from '@/utils/request'

// 查询知识库列表
export const getKnowledgeEntries = (params = {}) => {
  return request.get('/knowledge', { params })
}

// 获取知识库详情
export const getKnowledgeEntry = (id) => {
  return request.get(`/knowledge/${id}`)
}

// 手动创建知识库条目
export const createKnowledgeEntry = (data) => {
  return request.post('/knowledge', data)
}

// 更新知识库条目
export const updateKnowledgeEntry = (id, data) => {
  return request.put(`/knowledge/${id}`, data)
}

// 删除知识库条目
export const deleteKnowledgeEntry = (id) => {
  return request.delete(`/knowledge/${id}`)
}

// 上传资料文档并解析
export const uploadKnowledgeDocument = (data) => {
  return request.post('/knowledge/upload', data, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

// 语义/混合搜索
export const searchKnowledge = (data) => {
  return request.post('/knowledge/search', data)
}

// 生成嵌入
export const embedKnowledgeEntry = (id) => {
  return request.post(`/knowledge/${id}/embed`)
}

// AI 提取
export const extractKnowledgeEntry = (id) => {
  return request.post(`/knowledge/${id}/extract`)
}

// 智能推荐
export const recommendKnowledge = (data) => {
  return request.post('/knowledge/recommend', data)
}

// 获取分类建议列表
export const getKnowledgeCategories = () => {
  return request.get('/knowledge/categories')
}

// 获取标签建议列表
export const getKnowledgeTags = () => {
  return request.get('/knowledge/tags')
}

// 预览知识条目转换
export const previewConvertKnowledgeEntry = (id, data) => {
  return request.post(`/knowledge/${id}/convert/preview`, data)
}

// 执行知识条目转换
export const convertKnowledgeEntry = (id, data) => {
  return request.post(`/knowledge/${id}/convert`, data)
}
