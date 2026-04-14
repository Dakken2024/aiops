@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════════╗
echo ║   AiOps 环境搭建脚本 (Python 3.12 + PostgreSQL)     ║
echo ╚══════════════════════════════════════════════════════╝
echo.

:: ============================================================
:: Step 1: 创建 conda 虚拟环境 (Python 3.12)
:: ============================================================
echo [Step 1/4] 创建 conda 虚拟环境 aiops (Python 3.12)...
call conda activate base 2>nul
if errorlevel 1 (
    echo [错误] conda 未找到，请确保 Anaconda/Miniconda 已安装并加入 PATH
    pause
    exit /b 1
)

conda env list | findstr /i "aiops" >nul 2>&1
if not errorlevel 1 (
    echo   环境 aiops 已存在，跳过创建
) else (
    echo   正在创建新环境 (可能需要几分钟下载Python)...
    conda create -n aiops python=3.12 -y
    if errorlevel 1 (
        echo [错误] conda 环境创建失败
        pause
        exit /b 1
    )
)
echo   ✓ conda 环境 aiops 就绪
echo.

:: ============================================================
:: Step 2: 激活环境并安装依赖
:: ============================================================
echo [Step 2/4] 激活 aiops 环境并安装项目依赖...
call conda activate aiops
if errorlevel 1 (
    echo [错误] 无法激活 aiops 环境
    pause
    exit /b 1
)

python --version
echo.

echo   升级 pip ...
python -m pip install --upgrade pip -q

echo   安装 requirements.txt 依赖 (约需5-10分钟)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [警告] 部分依赖安装失败，请检查上方错误信息
) else (
    echo   ✓ 所有依赖安装成功
)
echo.

:: ============================================================
:: Step 3: 验证关键包
:: ============================================================
echo [Step 3/4] 验证关键依赖包...
set PASS=1
for %%P in (Django psycopg2 channels celery redis cryptography paramiko openai kubernetes scikit-learn statsmodels numpy pyyaml requests) do (
    python -c "import %%P; print('  ✓', '%%P')" 2>nul || (echo "  ✗ %%P 缺失" & set PASS=0)
)
if %PASS%==0 (
    echo.
    echo [警告] 存在缺失的依赖包，请检查安装日志
)
echo.

:: ============================================================
:: Step 4: 语法检查
:: ============================================================
echo [Step 4/4] 执行 Python 语法检查...
python -c "
import py_compile, os, sys

errors = []
base = r'%~dp0..\..'
skip_dirs = {'venv', '.git', '__pycache__', 'node_modules', '.env', 'migrations'}

for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                py_compile.compile(path, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(str(e))

print(f'\n检查了所有 .py 文件')
if errors:
    print(f'❌ 发现 {len(errors)} 个语法错误:')
    for e in errors:
        print(f'  {e}')
else:
    print('✅ 所有文件语法检查通过!')
"

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║   环境搭建完成!                                       ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo 后续操作:
echo   1. 激活环境:   conda activate aiops
echo   2. 启动开发:   python manage.py runserver
echo   3. 执行迁移:   python scripts\migration\run_migration.py --password 123456
echo   4. 切换PG模式:  set DB_ENGINE=postgresql ^&^& python manage.py runserver
echo.
pause
