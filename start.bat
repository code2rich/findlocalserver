@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set PYTHON=python
set HOST=0.0.0.0
set PORT=9999

:parse_args
if "%~1"=="" goto check_deps
if /i "%~1"=="-p" (
    set PORT=%~2
    shift & shift
    goto parse_args
)
if /i "%~1"=="--port" (
    set PORT=%~2
    shift & shift
    goto parse_args
)
if /i "%~1"=="--install" (
    echo 正在安装依赖...
    %PYTHON% -m pip install -r requirements.txt
    echo 安装完成
    exit /b 0
)
if /i "%~1"=="--help" goto usage
shift
goto parse_args

:check_deps
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 找不到 Python
    echo 请安装 Python 3.9+ 并确保已添加到 PATH
    exit /b 1
)

%PYTHON% -c "import fastapi" 2>nul
if errorlevel 1 (
    echo 依赖未安装，正在安装...
    %PYTHON% -m pip install -r requirements.txt
)

echo =====================================
echo   FindLocalServer 启动中...
echo   系统: Windows
echo   地址: http://localhost:%PORT%
echo   按 Ctrl+C 停止
echo =====================================
echo.
echo 提示: 如需管理员权限扫描端口，请以管理员身份运行
echo.

%PYTHON% main.py
goto :eof

:usage
echo FindLocalServer - 本地服务发现工具
echo.
echo 用法: %~nx0 [选项]
echo.
echo 选项:
echo   -p, --port PORT    指定端口 (默认: 9999)
echo   --install          安装 Python 依赖
echo   --help             显示帮助信息
echo.
echo 示例:
echo   %~nx0              # 启动服务 http://localhost:9999
echo   %~nx0 -p 8080      # 使用 8080 端口启动
echo   %~nx0 --install    # 安装依赖
echo.
echo 注意: 端口扫描功能需要管理员权限
