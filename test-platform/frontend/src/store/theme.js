import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  // 主题状态: 'light' | 'dark'
  const theme = ref(localStorage.getItem('theme') || 'light')
  
  // 切换主题
  const toggleTheme = () => {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }
  
  // 设置主题
  const setTheme = (newTheme) => {
    if (newTheme === 'light' || newTheme === 'dark') {
      theme.value = newTheme
    }
  }
  
  // 初始化主题
  const initTheme = () => {
    applyTheme(theme.value)
  }
  
  // 应用主题到DOM
  const applyTheme = (currentTheme) => {
    const html = document.documentElement
    if (currentTheme === 'dark') {
      html.classList.add('dark')
      html.classList.remove('light')
    } else {
      html.classList.add('light')
      html.classList.remove('dark')
    }
    localStorage.setItem('theme', currentTheme)
  }
  
  // 监听主题变化
  watch(theme, (newTheme) => {
    applyTheme(newTheme)
  }, { immediate: true })
  
  return {
    theme,
    toggleTheme,
    setTheme,
    initTheme
  }
})
