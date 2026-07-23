import request from '@/utils/request'

// 获取设备列表
export const getDevices = (params) => {
  return request.get('/devices', { params })
}

// 刷新设备
export const refreshDevices = () => {
  return request.post('/devices/refresh')
}

// 获取设备详情
export const getDeviceDetail = (serial) => {
  return request.get(`/devices/${serial}`)
}
