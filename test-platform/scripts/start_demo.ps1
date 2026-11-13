# ============================================================
#  测试平台 — 演示环境启动脚本（Windows / PowerShell）
#
#  演示专用：使用独立 demo.db + storage/demo/，**绝不触碰历史库**
#  backend/test_platform.db（其结构漂移在严格 init_db 下会 SchemaMismatchError
#  拒绝启动，属预期；严禁对任何真实库执行 alembic downgrade base）。
#
#  用法：
#    powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
#    powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1 -Port 8001
#    powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1 -SecretKey "<32+字符随机密钥>"
#    powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1 -MigrateOnly   # 仅建演示库后退出
#
#  环境变量（本脚本显式设置，覆盖 backend/.env 中的 DATABASE_URL 等）：
#    DATABASE_URL   = sqlite+aiosqlite:///./demo.db
#    STORAGE_PATH   = storage/demo
#    TOOLS_PATH     = storage/demo/tools
#    REPORTS_PATH   = storage/demo/reports
#    LOGS_PATH      = storage/demo/logs
#    TEST_TOOLS_PATH= ../test-tools   （只读工具清单校验用）
#  SECRET_KEY 解析顺序：-SecretKey 参数 > $env:DEMO_SECRET_KEY > $env:SECRET_KEY
#    > backend/.env 中的 SECRET_KEY > 本次运行临时生成（仅当次有效）
# ============================================================
param(
    [string]$SecretKey = "",
    [int]$Port = 8000,
    [switch]$SkipMigrate,
    [switch]$MigrateOnly,
    [string]$DemoDbPath = "./demo.db",
    [string]$StorageRoot = "storage/demo"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Error "未找到虚拟环境 $VenvPy，请先运行 start_windows.bat 或手动创建 .venv 并安装 backend/requirements.txt"
    exit 1
}

Write-Host "========== 测试平台 · 演示环境 ==========" -ForegroundColor Cyan
Write-Host "历史库 backend/test_platform.db 保留不动（只读）；演示使用独立 $DemoDbPath + $StorageRoot/"
Write-Host "注意：历史库存在结构漂移，严格 init_db 会 SchemaMismatchError 拒绝启动，属预期；严禁 alembic downgrade base。"

# ---------- 1. 演示环境变量（隔离） ----------
$env:DATABASE_URL = "sqlite+aiosqlite:///$DemoDbPath"
$env:STORAGE_PATH = $StorageRoot
$env:TOOLS_PATH = "$StorageRoot/tools"
$env:REPORTS_PATH = "$StorageRoot/reports"
$env:LOGS_PATH = "$StorageRoot/logs"
$env:TEST_TOOLS_PATH = "../test-tools"

# ---------- 2. SECRET_KEY ----------
function Get-EnvFileSecretKey([string]$envFile) {
    if (-not (Test-Path $envFile)) { return "" }
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*SECRET_KEY\s*=\s*(.+?)\s*$') { return $matches[1].Trim('"').Trim("'") }
    }
    return ""
}

if ($SecretKey) {
    $env:SECRET_KEY = $SecretKey
} elseif ($env:DEMO_SECRET_KEY) {
    $env:SECRET_KEY = $env:DEMO_SECRET_KEY
} elseif (-not $env:SECRET_KEY) {
    $fromFile = Get-EnvFileSecretKey (Join-Path $Backend ".env")
    if ($fromFile) {
        $env:SECRET_KEY = $fromFile
        Write-Host "[SECRET_KEY] 使用 backend/.env 中的密钥" -ForegroundColor DarkGray
    } else {
        $env:SECRET_KEY = (& $VenvPy -c "import secrets;print(secrets.token_urlsafe(48))")
        Write-Host "[SECRET_KEY] 未配置，已生成仅本次运行有效的临时随机密钥（如需持久化请写入 backend/.env）" -ForegroundColor Yellow
    }
}

# ---------- 3. 演示存储目录 ----------
New-Item -ItemType Directory -Force -Path "$StorageRoot/tools", "$StorageRoot/reports", "$StorageRoot/logs" | Out-Null

# ---------- 4. 首次/升级：alembic upgrade head（空库 001→004，幂等） ----------
if (-not $SkipMigrate) {
    Write-Host "[1/2] 初始化演示库（alembic upgrade head，空库 001→004，幂等）..."
    Push-Location $Backend
    try {
        & $VenvPy -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head 失败（退出码 $LASTEXITCODE）" }
        & $VenvPy -m alembic current
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[1/2] 跳过迁移（-SkipMigrate）"
}

# ---------- 5. 启动服务 ----------
Write-Host "[2/2] 启动演示服务..."
Write-Host "  演示库:      $Backend/$DemoDbPath"
Write-Host "  存储目录:    $Backend/$StorageRoot/{tools,reports,logs}"
Write-Host "  平台地址:    http://localhost:$Port"
Write-Host "  API 文档:    http://localhost:$Port/docs"
Write-Host "  首次使用请在登录页注册账号（首个注册用户自动成为管理员）。"
Write-Host "  提示：演示请只用只读测试项（如 cat /proc/meminfo），不要写入/烧录/重启/压测；daily/once 演示禁用。"
if ($MigrateOnly) {
    Write-Host "[MigrateOnly] 已完成演示库初始化，未启动服务。" -ForegroundColor Green
    exit 0
}

Push-Location $Backend
try {
    & $VenvPy -m uvicorn app.main:app --host 0.0.0.0 --port $Port
} finally {
    Pop-Location
}
