from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "Test Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # 安全配置
    # SECRET_KEY 无默认值：必须通过环境变量或 .env 配置，否则应用拒绝启动
    # （start_windows.bat 首次运行会自动生成随机密钥写入 backend/.env）。
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24小时

    # 开放注册开关：关闭时仅允许首个用户注册（自动成为 admin），
    # 后续账号由 admin 在用户管理中创建；开启后任何人可注册普通账号。
    REGISTRATION_ENABLED: bool = False

    # CORS 允许源（逗号分隔）。平台前后端同源部署，默认为空即不放开跨域；
    # 仅在前后端分离部署（如独立前端服务器）时才需要配置，例如：
    # ALLOWED_ORIGINS=http://192.168.1.10:3000,http://192.168.1.10:8080
    ALLOWED_ORIGINS: str = ""
    
    # 数据库配置（默认 SQLite，生产环境可切换为 PostgreSQL）
    DATABASE_URL: str = "sqlite+aiosqlite:///./test_platform.db"
    DATABASE_POOL_SIZE: int = 20
    
    # Redis配置
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery配置
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    
    # 文件存储配置
    STORAGE_PATH: str = "./storage"
    TOOLS_PATH: str = "./storage/tools"
    REPORTS_PATH: str = "./storage/reports"
    LOGS_PATH: str = "./storage/logs"  # 测试记录实时日志文件根目录
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB

    # 测试工具根目录（host_exec 类测试项的 {host_tool_dir} 默认解析为该目录的绝对路径）
    TEST_TOOLS_PATH: str = "../test-tools"

    # 前端静态文件目录：裸机默认相对 backend 工作目录指向 frontend/dist；
    # Docker 镜像内产物在 /app/static，通过环境变量 STATIC_PATH=static 覆盖。
    # 目录不存在时 main.py 跳过挂载（仅提供 API）并记 warning。
    STATIC_PATH: str = "../frontend/dist"
    
    # ADB配置
    ADB_TIMEOUT: int = 30
    ADB_RETRY_COUNT: int = 3
    # 设备心跳间隔（秒）：后台周期性对比 adb devices 与数据库设备状态
    HEARTBEAT_INTERVAL: int = 30
    # 任务调度器扫描间隔（秒）：后台周期性扫描 next_run_at 到期的调度任务
    SCHEDULER_INTERVAL: int = 30

    # LLM 配置
    LLM_PROVIDER: str = "openai"  # openai / deepseek / qwen 等
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-3.5-turbo"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2000
    LLM_TIMEOUT: int = 60

    # Embedding 配置
    EMBEDDING_ENABLED: bool = False
    EMBEDDING_PROVIDER: str = "openai"  # openai / local / mock
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    EMBEDDING_TIMEOUT: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
