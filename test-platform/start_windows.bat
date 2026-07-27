@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  测试平台 Windows 一键启动脚本
REM  - 自动创建/复用虚拟环境（.venv）
REM  - 自动安装后端依赖
REM  - 首次运行自动生成随机 SECRET_KEY 写入 backend\.env
REM  - 前端产物缺失且本机有 npm 时自动构建
REM  - 启动后浏览器访问 http://localhost:8000
REM ============================================================

cd /d "%~dp0"
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "VENV=%ROOT%.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "DIST=%ROOT%frontend\dist"

echo ========== 测试平台启动 ==========

REM ---------- 1. 检查 Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
)

REM ---------- 2. 创建虚拟环境 ----------
if not exist "%VENV_PY%" (
    echo [1/5] 创建虚拟环境 .venv ...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败。
        pause
        exit /b 1
    )
) else (
    echo [1/5] 虚拟环境已存在，跳过创建。
)

REM ---------- 3. 安装后端依赖 ----------
echo [2/5] 安装/校验后端依赖...
"%VENV_PY%" -m pip install --quiet --upgrade pip
"%VENV_PY%" -m pip install --quiet -r "%BACKEND%\requirements.txt"
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

REM ---------- 4. 首次运行生成 .env（随机 SECRET_KEY） ----------
if not exist "%BACKEND%\.env" (
    echo [3/5] 生成 backend\.env（随机 SECRET_KEY）...
    "%VENV_PY%" -c "import secrets,pathlib; pathlib.Path(r'%BACKEND%\.env').write_text('SECRET_KEY=' + secrets.token_urlsafe(48) + '\n', encoding='utf-8')"
) else (
    echo [3/5] backend\.env 已存在，跳过。
)

REM ---------- 5. 检查前端产物 ----------
if exist "%DIST%\index.html" (
    echo [4/5] 前端产物已存在。
) else (
    echo [4/5] 前端产物不存在，尝试构建...
    where npm >nul 2>nul
    if errorlevel 1 (
        echo [警告] 未找到 npm，跳过前端构建，本次仅提供 API（http://localhost:8000/docs）。
    ) else (
        pushd "%ROOT%frontend"
        call npm ci && call npm run build
        popd
        if not exist "%DIST%\index.html" (
            echo [警告] 前端构建失败，本次仅提供 API（http://localhost:8000/docs）。
        )
    )
)

REM ---------- 6. 启动服务 ----------
echo [5/5] 启动服务...
echo.
echo   平台地址:  http://localhost:8000
echo   API 文档:  http://localhost:8000/docs
echo   首次使用请在登录页注册账号（首个注册用户自动成为管理员）。
echo   按 Ctrl+C 停止服务。
echo.
cd /d "%BACKEND%"
"%VENV_PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

endlocal
