// ESLint 最小配置：Vue3 推荐集 + 宽松档位。
// 存量代码暂不强制修复，风格类/约定类规则降级为 warn 或关闭，
// 只保留真正的错误级检查（未定义变量、语法错误等）。
module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-recommended',
  ],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  globals: {
    // playwright e2e 全局（tests/e2e）
    process: 'readonly',
  },
  rules: {
    // 存量代码风格：降级为 warn，逐步收敛
    'vue/multi-word-component-names': 'off',
    'vue/require-default-prop': 'warn',
    'vue/require-prop-types': 'warn',
    'vue/attributes-order': 'warn',
    'vue/order-in-components': 'warn',
    'vue/this-in-template': 'warn',
    'vue/attribute-hyphenation': 'warn',
    'vue/v-on-event-hyphenation': 'warn',
    'vue/component-definition-name-casing': 'warn',
    'vue/html-self-closing': 'warn',
    'vue/max-attributes-per-line': 'warn',
    'vue/singleline-html-element-content-newline': 'warn',
    'vue/html-indent': 'warn',
    'vue/html-closing-bracket-newline': 'warn',
    'vue/first-attribute-linebreak': 'warn',
    'vue/no-v-html': 'warn',
    'no-unused-vars': 'warn',
    'no-empty': 'warn',
  },
}
