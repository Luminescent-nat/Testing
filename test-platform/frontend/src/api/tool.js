import request from '@/utils/request'

// 获取测试工具列表
export const getTools = (params) => {
  return request.get('/tools', { params })
}

// 获取工具详情
export const getToolDetail = (id) => {
  return request.get(`/tools/${id}`)
}

// 上传测试工具
export const uploadTool = (data) => {
  return request.post('/tools', data, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

// 删除测试工具
export const deleteTool = (id) => {
  return request.delete(`/tools/${id}`)
}
