import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login, getUserInfo } from '@/api/auth'
import { isSuccessResponse, withPcIdentifier } from '@/api/client'
import router from '@/router'

export const useUserStore = defineStore('user', () => {
  // State
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(null)
  
  // Getters
  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => userInfo.value?.role === 'admin')
  
  // Actions
  const setToken = (newToken) => {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }
  
  const clearToken = () => {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
  }
  
  const loginAction = async (credentials) => {
    const res = await login(withPcIdentifier(credentials))
    if (isSuccessResponse(res)) {
      setToken(res.data.access_token)
      userInfo.value = res.data.user
      return true
    }
    return false
  }
  
  const logout = () => {
    clearToken()
    router.push('/login')
  }
  
  const fetchUserInfo = async () => {
    if (!token.value) return
    try {
      const res = await getUserInfo()
      if (isSuccessResponse(res)) {
        userInfo.value = res.data
      }
    } catch (error) {
      console.error('获取用户信息失败:', error)
    }
  }
  
  // 初始化时获取用户信息
  if (token.value) {
    fetchUserInfo()
  }
  
  return {
    token,
    userInfo,
    isLoggedIn,
    isAdmin,
    setToken,
    clearToken,
    loginAction,
    logout,
    fetchUserInfo
  }
})
