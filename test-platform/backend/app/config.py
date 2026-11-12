from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

# T-18：SECRET_KEY 强度规则（docs/design/scheduler-and-data.md 第 6 节）
SECRET_KEY_MIN_LENGTH = 32
# Compose / 文档示例中出现过的占位值，一律拒绝（比较时忽略大小写、下划线/连字符）
SECRET_KEY_PLACEHOLDERS = frozenset(
    {
        "secret",
        "change-me",
        "changeme",
        "change-me-in-production",
        "your-secret-key",
        "your-secret-key-here",
        "please-change-me",
        "please-change-me-in-production",
        "pleasechangemeinproduction",
        "default-secret",
        "insecure-secret",
    }
)


class WeakSecretKeyError(ValueError):
    """SECRET_KEY 强度校验失败（错误信息只指出配置项，绝不回显密钥值）。"""


def secret_key_problem(secret_key: Optional[str]) -> Optional[str]:
    """返回 SECRET_KEY 不合规的原因；合规返回 None。返回值绝不包含密钥值本身。"""
    if secret_key is None or not secret_key.strip():
        return "SECRET_KEY 未配置（空值），应用拒绝启动"
    if len(secret_key) < SECRET_KEY_MIN_LENGTH:
        return f"SECRET_KEY 强度不足：长度必须至少 {SECRET_KEY_MIN_LENGTH} 字符"
    normalized = secret_key.strip().lower().replace("_", "-")
    # 精确占位值，或以占位值开头的「改了一下但仍是示例」变体，一律拒绝
    if normalized in SECRET_KEY_PLACEHOLDERS or any(
        normalized.startswith(placeholder + "-") for placeholder in SECRET_KEY_PLACEHOLDERS
    ):
        return "SECRET_KEY 是已知的示例/占位值，禁止用于开发或生产"
    if len(set(secret_key.strip())) == 1:
        return "SECRET_KEY 为单字符重复，熵不足"
    return None


def assert_secret_key_strength(secret_key: Optional[str]) -> None:
    """校验 SECRET_KEY 强度；不合规抛 WeakSecretKeyError（信息不含密钥值）。"""
    problem = secret_key_problem(secret_key)
    if problem is not None:
        raise WeakSecretKeyError(
            f"{problem}。请生成随机密钥并写入 backend/.env（compose 场景写入 .env 或环境变量），"
            '例如：python -c "import secrets; print(\'SECRET_KEY=\' + secrets.token_urlsafe(48))"'
        )


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
