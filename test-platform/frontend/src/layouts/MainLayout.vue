<template>
  <div class="app-wrapper">
    <template v-if="$route.path === '/login'">
      <router-view />
    </template>

    <el-container v-else class="main-container">
      <el-aside width="220px" class="sidebar">
        <div class="sidebar-header">
          <div class="logo-box">
            <el-icon :size="24" color="#fff"><Monitor /></el-icon>
          </div>
          <span class="sidebar-title">测试平台</span>
        </div>

        <el-menu
          :default-active="activeMenu"
          class="sidebar-menu"
          router
          background-color="transparent"
          :text-color="menuTextColor"
          :active-text-color="menuActiveColor"
        >
          <el-menu-item index="/dashboard">
            <el-icon><Odometer /></el-icon>
            <span>仪表盘</span>
          </el-menu-item>

          <el-menu-item index="/devices">
            <el-icon><Cellphone /></el-icon>
            <span>设备管理</span>
          </el-menu-item>

          <el-menu-item index="/modules">
            <el-icon><Grid /></el-icon>
            <span>测试模块</span>
          </el-menu-item>

          <el-menu-item index="/tasks">
            <el-icon><List /></el-icon>
            <span>测试任务</span>
          </el-menu-item>

          <el-menu-item index="/ai-test">
            <el-icon><MagicStick /></el-icon>
            <span>AI 测试</span>
          </el-menu-item>

          <el-menu-item index="/reports">
            <el-icon><Document /></el-icon>
            <span>测试报告</span>
          </el-menu-item>

          <el-menu-item index="/memory">
            <el-icon><Collection /></el-icon>
            <span>基线知识库</span>
          </el-menu-item>

          <el-menu-item index="/knowledge">
            <el-icon><Notebook /></el-icon>
            <span>测试知识库</span>
          </el-menu-item>

          <el-sub-menu index="/admin" v-if="userStore.isAdmin">
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>系统管理</span>
            </template>
            <el-menu-item index="/admin/users">
              <span>用户管理</span>
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-aside>

      <el-container class="content-container">
        <el-header class="navbar" height="60px">
          <div class="navbar-left">
            <breadcrumb />
          </div>

          <div class="navbar-right">
            <el-tooltip :content="isDark ? '切换亮色' : '切换暗色'">
              <el-button
                circle
                :icon="isDark ? Sunny : Moon"
                @click="toggleTheme"
                class="theme-btn"
              />
            </el-tooltip>

            <el-tooltip content="全屏">
              <el-button
                circle
                :icon="FullScreen"
                @click="toggleFullscreen"
                class="action-btn"
              />
            </el-tooltip>

            <el-dropdown @command="handleCommand">
              <div class="user-info">
                <el-avatar :size="32" :icon="UserFilled" />
                <span class="username">{{ userStore.userInfo?.username || '用户' }}</span>
                <el-icon><ArrowDown /></el-icon>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">
                    <el-icon><User /></el-icon>个人信息
                  </el-dropdown-item>
                  <el-dropdown-item divided command="logout">
                    <el-icon><SwitchButton /></el-icon>退出登录
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </el-header>

        <el-main class="main-content">
          <router-view v-slot="{ Component }">
            <transition name="fade-transform" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Monitor, Odometer, Cellphone, Grid, List, Document,
  Collection, Notebook, Setting, User, UserFilled, ArrowDown, SwitchButton,
  Moon, Sunny, FullScreen, MagicStick
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { useThemeStore } from '@/store/theme'
import Breadcrumb from '@/components/Breadcrumb.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const themeStore = useThemeStore()

const activeMenu = computed(() => route.path)
const isDark = computed(() => themeStore.theme === 'dark')
const menuTextColor = computed(() => isDark.value ? '#94a3b8' : '#475569')
const menuActiveColor = computed(() => '#2563eb')

const toggleTheme = () => {
  themeStore.toggleTheme()
}

const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

const handleCommand = (command) => {
  switch (command) {
    case 'profile':
      router.push('/profile')
      break
    case 'logout':
      userStore.logout()
      break
  }
}
</script>

<style scoped>
.app-wrapper {
  width: 100%;
  height: 100%;
}

.main-container {
  width: 100%;
  height: 100vh;
}

.sidebar {
  background-color: var(--tp-bg-elevated);
  border-right: 1px solid var(--tp-border);
  display: flex;
  flex-direction: column;
  transition: background-color 0.3s, border-color 0.3s;
}

.sidebar-header {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  border-bottom: 1px solid var(--tp-border);
  gap: 12px;
}

.logo-box {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--tp-primary) 0%, var(--tp-primary-light) 100%);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px var(--tp-primary-soft);
}

.sidebar-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--tp-text);
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  padding: 12px 10px;
}

.sidebar-menu :deep(.el-menu-item),
.sidebar-menu :deep(.el-sub-menu__title) {
  border-radius: 8px;
  margin-bottom: 4px;
  height: 46px;
  line-height: 46px;
}

.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-sub-menu__title:hover) {
  background-color: var(--tp-bg-page);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background-color: var(--tp-primary-soft);
}

.content-container {
  background-color: var(--tp-bg-page);
  transition: background-color 0.3s;
}

.navbar {
  background-color: var(--tp-bg-elevated);
  border-bottom: 1px solid var(--tp-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  transition: background-color 0.3s, border-color 0.3s;
}

.navbar-left {
  display: flex;
  align-items: center;
}

.navbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.theme-btn,
.action-btn {
  background: var(--tp-bg-page);
  border-color: var(--tp-border);
  color: var(--tp-text-secondary);
  transition: all 0.2s;
}

.theme-btn:hover,
.action-btn:hover {
  color: var(--tp-primary);
  border-color: var(--tp-primary);
  background: var(--tp-primary-soft);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 5px 10px;
  border-radius: 8px;
  transition: background-color 0.3s;
}

.user-info:hover {
  background-color: var(--tp-bg-page);
}

.username {
  font-size: 14px;
  color: var(--tp-text-secondary);
}

.main-content {
  padding: 20px;
  overflow-y: auto;
}

/* 页面切换动画 */
.fade-transform-enter-active,
.fade-transform-leave-active {
  transition: all 0.3s;
}

.fade-transform-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>