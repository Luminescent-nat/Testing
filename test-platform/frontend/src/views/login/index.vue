<template>
  <div class="login-page" :class="{ dark: isDark }">
    <!-- 背景 -->
    <div class="bg-layer">
      <div class="ambient-glow glow-1"></div>
      <div class="ambient-glow glow-2"></div>
    </div>

    <!-- 右上角主题切换 -->
    <div class="top-tools">
      <el-tooltip :content="isDark ? '切换亮色' : '切换暗色'" placement="left">
        <button class="tool-btn" @click="toggleTheme">
          <el-icon v-if="isDark"><Sunny /></el-icon>
          <el-icon v-else><Moon /></el-icon>
        </button>
      </el-tooltip>
    </div>

    <!-- 主卡片 -->
    <div class="login-card">
      <!-- 左侧：水豚噜噜 -->
      <div class="card-left">
        <div class="image-frame">
          <img src="/capybara-lulu-hd.png" alt="水豚噜噜" />
        </div>
        <div class="left-caption">
          <h2>Test Platform</h2>
          <p>智能硬件 · 自动化测试</p>
        </div>
      </div>

      <!-- 右侧：登录/注册 -->
      <div class="card-right">
        <div class="brand-mini">
          <div class="brand-icon">
            <el-icon size="20" color="#fff"><Cpu /></el-icon>
          </div>
          <span class="brand-name">测试平台</span>
        </div>

        <h1 class="welcome-title">欢迎回来</h1>
        <p class="welcome-desc">请登录或注册您的账号</p>

        <!-- 标签切换 -->
        <div class="tabs">
          <button
            type="button"
            class="tab-btn"
            :class="{ active: !isRegister }"
            @click="isRegister = false"
          >
            登录
          </button>
          <button
            type="button"
            class="tab-btn"
            :class="{ active: isRegister }"
            @click="isRegister = true"
          >
            注册
          </button>
          <div class="tab-slider" :class="{ right: isRegister }"></div>
        </div>

        <form @submit.prevent="handleSubmit" class="auth-form">
          <div class="form-group">
            <label>用户名</label>
            <div class="input-box">
              <el-icon class="field-icon"><User /></el-icon>
              <input
                v-model="form.username"
                type="text"
                placeholder="请输入用户名"
                autocomplete="username"
                required
                minlength="3"
              />
            </div>
          </div>

          <div class="form-group">
            <label>密码</label>
            <div class="input-box">
              <el-icon class="field-icon"><Lock /></el-icon>
              <input
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码"
                autocomplete="current-password"
                required
                minlength="6"
              />
              <button
                type="button"
                class="eye-btn"
                @click="showPassword = !showPassword"
                tabindex="-1"
              >
                <el-icon v-if="showPassword"><View /></el-icon>
                <el-icon v-else><Hide /></el-icon>
              </button>
            </div>
          </div>

          <div class="form-group" v-if="isRegister">
            <label>确认密码</label>
            <div class="input-box">
              <el-icon class="field-icon"><Lock /></el-icon>
              <input
                v-model="form.confirmPassword"
                :type="showConfirm ? 'text' : 'password'"
                placeholder="请再次输入密码"
                autocomplete="new-password"
                required
                minlength="6"
              />
              <button
                type="button"
                class="eye-btn"
                @click="showConfirm = !showConfirm"
                tabindex="-1"
              >
                <el-icon v-if="showConfirm"><View /></el-icon>
                <el-icon v-else><Hide /></el-icon>
              </button>
            </div>
          </div>

          <p class="hint" v-if="isRegister">首个注册账号将自动成为管理员</p>

          <button type="submit" class="submit-btn" :disabled="loading">
            <span v-if="loading" class="spinner"></span>
            <span>{{ loading ? '处理中...' : (isRegister ? '注 册' : '登 录') }}</span>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Cpu, User, Lock, View, Hide, Sunny, Moon
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { useThemeStore } from '@/store/theme'
import { login, register } from '@/api'

const router = useRouter()
const userStore = useUserStore()
const themeStore = useThemeStore()

const isDark = computed(() => themeStore.theme === 'dark')
const toggleTheme = () => themeStore.toggleTheme()

const isRegister = ref(false)
const loading = ref(false)
const showPassword = ref(false)
const showConfirm = ref(false)

const form = reactive({
  username: '',
  password: '',
  confirmPassword: ''
})

watch(isRegister, () => {
  form.password = ''
  form.confirmPassword = ''
  showPassword.value = false
  showConfirm.value = false
})

const validate = () => {
  if (!form.username || form.username.length < 3) {
    ElMessage.warning('用户名至少需要 3 个字符')
    return false
  }
  if (!form.password || form.password.length < 6) {
    ElMessage.warning('密码至少需要 6 个字符')
    return false
  }
  if (isRegister.value && form.password !== form.confirmPassword) {
    ElMessage.warning('两次输入的密码不一致')
    return false
  }
  return true
}

const handleSubmit = async () => {
  if (!validate()) return

  loading.value = true
  try {
    if (isRegister.value) {
      const res = await register({
        username: form.username,
        password: form.password
      })
      if (res.code === 200) {
        ElMessage.success(`注册成功，角色：${res.data.role}，请登录`)
        isRegister.value = false
      }
    } else {
      const res = await login({
        username: form.username,
        password: form.password
      })
      if (res.code === 200) {
        userStore.setToken(res.data.access_token)
        userStore.userInfo = res.data.user
        ElMessage.success('登录成功')
        router.push('/dashboard')
      }
    }
  } catch (error) {
    console.error(isRegister.value ? '注册失败:' : '登录失败:', error)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--tp-bg-page);
  color: var(--tp-text);
  overflow: hidden;
  transition: background 0.4s ease, color 0.4s ease;
}

/* 背景 */
.bg-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.ambient-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.5;
  transition: opacity 0.4s ease;
}

.glow-1 {
  width: 500px;
  height: 500px;
  top: -150px;
  right: -100px;
  background: radial-gradient(circle, var(--tp-primary) 0%, transparent 70%);
  opacity: 0.12;
}

.glow-2 {
  width: 400px;
  height: 400px;
  bottom: -100px;
  left: -100px;
  background: radial-gradient(circle, var(--tp-info) 0%, transparent 70%);
  opacity: 0.1;
}

.dark .ambient-glow {
  opacity: 0.8;
}

.dark .glow-1 {
  opacity: 0.25;
}

/* 右上角工具 */
.top-tools {
  position: absolute;
  top: 24px;
  right: 24px;
  z-index: 10;
}

.tool-btn {
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--tp-bg-elevated);
  border: 1px solid var(--tp-border);
  border-radius: 50%;
  color: var(--tp-text-secondary);
  cursor: pointer;
  font-size: 18px;
  transition: all 0.2s;
  box-shadow: var(--tp-shadow-sm);
}

.tool-btn:hover {
  color: var(--tp-primary);
  border-color: var(--tp-primary);
  transform: translateY(-2px);
  box-shadow: var(--tp-shadow);
}

/* 登录卡片 */
.login-card {
  position: relative;
  z-index: 5;
  display: flex;
  width: 900px;
  min-height: 600px;
  max-height: 92vh;
  background: var(--tp-bg-elevated);
  border: 1px solid var(--tp-border);
  border-radius: 28px;
  box-shadow: var(--tp-shadow-lg);
  overflow: hidden;
}

/* 左侧 */
.card-left {
  width: 45%;
  background: linear-gradient(135deg, var(--tp-primary-soft) 0%, transparent 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  position: relative;
}

.image-frame {
  width: 280px;
  height: 280px;
  border-radius: 50%;
  background: var(--tp-bg-page);
  border: 2px solid var(--tp-border);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--tp-shadow);
  overflow: hidden;
  margin-bottom: 30px;
}

.image-frame img {
  width: 90%;
  height: 90%;
  object-fit: contain;
  transition: transform 0.3s ease;
}

.image-frame:hover img {
  transform: scale(1.05);
}

.left-caption {
  text-align: center;
}

.left-caption h2 {
  font-size: 22px;
  font-weight: 700;
  color: var(--tp-text);
  margin: 0 0 6px 0;
}

.left-caption p {
  font-size: 13px;
  color: var(--tp-text-secondary);
  margin: 0;
}

/* 右侧 */
.card-right {
  flex: 1;
  padding: 45px 55px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  max-height: 90vh;
}

.brand-mini {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.brand-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--tp-primary) 0%, var(--tp-primary-light) 100%);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px var(--tp-primary-soft);
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--tp-text);
}

.welcome-title {
  font-size: 28px;
  font-weight: 600;
  color: var(--tp-text);
  margin: 0 0 6px 0;
}

.welcome-desc {
  font-size: 14px;
  color: var(--tp-text-secondary);
  margin: 0 0 20px 0;
}

/* 标签切换 */
.tabs {
  position: relative;
  display: flex;
  background: var(--tp-bg-page);
  border-radius: 12px;
  padding: 4px;
  margin-bottom: 18px;
}

.tab-btn {
  flex: 1;
  height: 40px;
  border: none;
  background: transparent;
  color: var(--tp-text-secondary);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 10px;
  transition: color 0.3s;
  position: relative;
  z-index: 2;
}

.tab-btn.active {
  color: #fff;
}

.tab-slider {
  position: absolute;
  top: 4px;
  left: 4px;
  width: calc(50% - 4px);
  height: 40px;
  background: linear-gradient(135deg, var(--tp-primary) 0%, var(--tp-primary-light) 100%);
  border-radius: 10px;
  box-shadow: var(--tp-shadow);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 1;
}

.tab-slider.right {
  transform: translateX(100%);
}

/* 表单 */
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 13px;
  color: var(--tp-text-secondary);
  font-weight: 500;
}

.input-box {
  position: relative;
  display: flex;
  align-items: center;
}

.field-icon {
  position: absolute;
  left: 14px;
  color: var(--tp-text-tertiary);
  font-size: 18px;
}

.input-box input {
  width: 100%;
  height: 48px;
  padding: 0 44px;
  background: var(--tp-bg-page);
  border: 1px solid var(--tp-border);
  border-radius: 12px;
  color: var(--tp-text);
  font-size: 14px;
  outline: none;
  box-sizing: border-box;
  transition: all 0.2s;
}

.input-box input::placeholder {
  color: var(--tp-text-tertiary);
}

.input-box input:focus {
  border-color: var(--tp-primary);
  background: var(--tp-bg-elevated);
  box-shadow: 0 0 0 3px var(--tp-primary-soft);
}

/* 隐藏浏览器默认的密码显示按钮，只保留自定义的眼睛按钮 */
.input-box input::-ms-reveal,
.input-box input::-ms-clear {
  display: none;
}

.input-box input::-webkit-textfield-decoration-container {
  visibility: hidden;
}

.eye-btn {
  position: absolute;
  right: 12px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--tp-text-tertiary);
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s;
}

.eye-btn:hover {
  color: var(--tp-text);
  background: var(--tp-border-light);
}

.hint {
  margin: -4px 0 0;
  font-size: 12px;
  color: var(--tp-text-tertiary);
  text-align: center;
}

.submit-btn {
  width: 100%;
  height: 48px;
  margin-top: 4px;
  background: linear-gradient(135deg, var(--tp-primary) 0%, var(--tp-primary-light) 100%);
  border: none;
  border-radius: 12px;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  box-shadow: var(--tp-shadow-glow);
  transition: all 0.3s;
}

.submit-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 30px var(--tp-primary-soft);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 响应式 */
@media (max-width: 950px) {
  .login-card {
    width: 420px;
    height: auto;
  }

  .card-left {
    display: none;
  }

  .card-right {
    padding: 35px 30px;
  }
}

@media (max-width: 480px) {
  .login-card {
    width: 100%;
    height: 100%;
    border-radius: 0;
    border: none;
  }

  .card-right {
    padding: 30px 25px;
    justify-content: center;
  }

  .top-tools {
    top: 16px;
    right: 16px;
  }
}
</style>