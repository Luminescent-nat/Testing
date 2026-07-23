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

// 修改密码
export const changePassword = (data) => {
  return request.post('/auth/change-password', data)
}
