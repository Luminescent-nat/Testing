import request from '@/utils/request'

// 获取用户列表
export const getUsers = (params) => {
  return request.get('/users', { params })
}

// 更新用户信息（角色/状态）
export const updateUser = (id, data) => {
  return request.put(`/users/${id}`, data)
}

// 重置用户密码
export const resetUserPassword = (id, newPassword) => {
  return request.post(`/users/${id}/reset-password`, null, {
    params: { new_password: newPassword }
  })
}

// 删除用户（软删除）
export const deleteUser = (id) => {
  return request.delete(`/users/${id}`)
}
