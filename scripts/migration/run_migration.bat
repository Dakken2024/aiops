@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════╗
echo ║   AiOps SQLite → PostgreSQL 18 一键迁移工具     ║
echo ╚══════════════════════════════════════════════════╝
echo.

:: 设置项目根目录
cd /d "%~dp0..\.."
set AIOPS_ROOT=%CD%

:: 默认配置 (可修改)
set PG_HOST=localhost
set PG_PORT=5432
set PG_USER=postgres
set PG_PASSWORD=123456
set PG_DB=aiops_db

:: 解析命令行参数
:parse_args
if "%~1"=="" goto :start
if "%~1"=="--host" set PG_HOST=%~2 & shift & shift & goto :parse_args
if "%~1"=="--port" set PG_PORT=%~2 & shift & shift & goto :parse_args
if "%~1"=="--user" set PG_USER=%~2 & shift & shift & goto :parse_args
if "%~1"=="--password" set PG_PASSWORD=%~2 & shift & shift & goto :parse_args
if "%~1"=="--db" set PG_DB=%~2 & shift & shift & goto :parse_args
if "%~1"=="--skip-backup" set SKIP_BACKUP=1 & shift & goto :parse_args
shift
goto :parse_args

:start
echo 目标数据库: postgresql://%PG_USER%@%PG_HOST%:%PG_PORT%/%PG_DB%
echo 项目目录: %AIOPS_ROOT%
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 未安装或不在 PATH 中
    pause
    exit /b 1
)

:: 检查 psycopg2
python -c "import psycopg2" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装 psycopg2-binary...
    pip install psycopg2-binary==2.9.9 --user
    if errorlevel 1 (
        echo [错误] psycopg2 安装失败，请手动运行: pip install psycopg2-binary==2.9.9
        pause
        exit /b 1
    )
)

:: 构建迁移命令
set MIGRATE_CMD=python scripts\migration\run_migration.py --host %PG_HOST% --port %PG_PORT% --user %PG_USER% --password %PG_PASSWORD% --dbname %PG_DB%

if defined SKIP_BACKUP (
    set MIGRATE_CMD=!MIGRATE_CMD! --skip-backup
)

echo.
echo 开始执行迁移...
echo ================================================
%MIGRATE_CMD%

if errorlevel 1 (
    echo.
    echo ================================================
    echo [失败] 迁移过程中出现错误，请查看上方日志
    echo.
) else (
    echo.
    echo ================================================
    echo [成功] 迁移完成!
    echo.
    echo 启动 PostgreSQL 模式:
    echo   set DB_ENGINE=postgresql ^&^& python manage.py runserver
)

pause
