<template>
  <div class="error-page">
    <div class="error-content">
      <div class="error-code">404</div>
      <div class="error-title">页面不存在</div>
      <div class="error-desc">
        抱歉，您访问的页面已丢失或不存在
      </div>
      <el-button type="primary" size="large" @click="goHome">
        <el-icon><HomeFilled /></el-icon>
        返回首页
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { HomeFilled } from '@element-plus/icons-vue'

const router = useRouter()

const goHome = () => {
  router.push('/')
}
</script>

<style scoped lang="scss">
.error-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--tp-bg-page);
  
  .error-content {
    text-align: center;
    padding: 40px;
    
    .error-code {
      font-size: 120px;
      font-weight: bold;
      color: var(--el-color-primary);
      line-height: 1;
      margin-bottom: 20px;
      opacity: 0.8;
    }
    
    .error-title {
      font-size: 28px;
      color: var(--tp-text);
      margin-bottom: 15px;
    }
    
    .error-desc {
      font-size: 16px;
      color: var(--tp-text-secondary);
      margin-bottom: 30px;
    }
    
    .el-button {
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
  }
}
</style>
