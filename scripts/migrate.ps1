#Requires -Version 5.1
# =============================================================================
# AiOps SQLite → PostgreSQL 一键迁移脚本 (PowerShell 版本)
# =============================================================================
# 覆盖完整流程：
#   1. 停止应用服务（可选）
#   2. 备份 SQLite（复制 db.sqlite3）
#   3. 运行 pre_migration_cleanup.py
#   4. 从 SQLite dumpdata 导出 JSON
#   5. 切换配置到 PostgreSQL
#   6. 执行 migrate 创建表结构
#   7. 执行 loaddata 导入数据
#   8. 执行 sqlsequencereset 更新序列
#   9. 运行 post_migration_validation.py（如果存在）
# =============================================================================

[CmdletBinding()]
param(
    [string]$PgHost = $env:PG_HOST,
    [int]$PgPort = 5432,
    [string]$PgUser = $env:PG_USER,
    [string]$PgPassword = $env:PG_PASSWORD,
    [string]$PgDb = $env:PG_DB,
    [string]$AppService = $env:APP_SERVICE,
    [switch]$SkipBackup
)

# 默认值
if (-not $PgHost) { $PgHost = 'localhost' }
if (-not $PgPort) { $PgPort = 5432 }
if (-not $PgUser) { $PgUser = 'postgres' }
if (-not $PgPassword) { $PgPassword = '' }
if (-not $PgDb) { $PgDb = 'aiops_db' }

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackupDir = Join-Path $ProjectRoot "backups" (Get-Date -Format "yyyyMMdd_HHmmss")
$LogFile = Join-Path $BackupDir "migration.log"
$DumpFile = Join-Path $BackupDir "dumpdata.json"
$SettingsModule = "ops_platform.settings"

# Django 环境变量
$env:DJANGO_SETTINGS_MODULE = $SettingsModule
$env:PYTHONPATH = "$ProjectRoot;$($env:PYTHONPATH)"

# ---------------------------------------------------------------------------
# 日志函数
# ---------------------------------------------------------------------------
function Write-Log {
    param(
        [string]$Message,
        [ValidateSet('Info','Ok','Warn','Error')]
        [string]$Level = 'Info'
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    switch ($Level) {
        'Info'  { $prefix = "[INFO]  "; $color = 'Cyan' }
        'Ok'    { $prefix = "[OK]    "; $color = 'Green' }
        'Warn'  { $prefix = "[WARN]  "; $color = 'Yellow' }
        'Error' { $prefix = "[ERROR] "; $color = 'Red' }
    }
    $line = "$timestamp $prefix$Message"
    Write-Host $line -ForegroundColor $color
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    }
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------
$ErrorActionPreference = 'Stop'

try {
    # -----------------------------------------------------------------------
    # 步骤 1: 停止应用服务（可选）
    # -----------------------------------------------------------------------
    Write-Log "============================================================" 'Info'
    Write-Log "AiOps 数据库迁移: SQLite → PostgreSQL" 'Info'
    Write-Log "目标: postgresql://${PgUser}@${PgHost}:${PgPort}/${PgDb}" 'Info'
    Write-Log "日志: $LogFile" 'Info'
    Write-Log "============================================================" 'Info'

    if ($AppService) {
        Write-Log "[Step 1/9] 停止应用服务: $AppService" 'Info'
        try {
            Stop-Service -Name $AppService -Force -ErrorAction Stop
            Write-Log "应用服务已停止" 'Ok'
        }
        catch {
            Write-Log "停止应用服务失败: $_ 继续执行..." 'Warn'
        }
    }
    else {
        Write-Log "[Step 1/9] 跳过停止应用服务（未配置 APP_SERVICE）" 'Info'
    }

    # -----------------------------------------------------------------------
    # 步骤 2: 备份 SQLite
    # -----------------------------------------------------------------------
    Write-Log "[Step 2/9] 备份 SQLite 数据库" 'Info'
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

    $SqliteDb = Join-Path $ProjectRoot "db.sqlite3"
    if (Test-Path $SqliteDb) {
        if (-not $SkipBackup) {
            Copy-Item $SqliteDb (Join-Path $BackupDir "db.sqlite3.bak") -Force
            Write-Log "SQLite 备份完成: $(Join-Path $BackupDir 'db.sqlite3.bak')" 'Ok'
        }
        else {
            Write-Log "跳过备份（--SkipBackup 已指定）" 'Warn'
        }
    }
    else {
        Write-Log "未找到 db.sqlite3，跳过备份" 'Warn'
    }

    $SettingsFile = Join-Path $ProjectRoot "ops_platform" "settings.py"
    if (Test-Path $SettingsFile) {
        Copy-Item $SettingsFile (Join-Path $BackupDir "settings.py.bak") -Force
        Write-Log "settings.py 备份完成" 'Ok'
    }

    # -----------------------------------------------------------------------
    # 步骤 3: 运行迁移前数据清洗
    # -----------------------------------------------------------------------
    Write-Log "[Step 3/9] 运行迁移前数据清洗" 'Info'
    $CleanupScript = Join-Path $ScriptDir "pre_migration_cleanup.py"
    if (-not (Test-Path $CleanupScript)) {
        throw "未找到清洗脚本: $CleanupScript"
    }

    $proc = Start-Process -FilePath "python" -ArgumentList $CleanupScript -WorkingDirectory $ProjectRoot -Wait -PassThru -NoNewWindow -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile
    if ($proc.ExitCode -ne 0) {
        throw "数据清洗失败，退出码: $($proc.ExitCode)"
    }
    Write-Log "数据清洗完成" 'Ok'

    # -----------------------------------------------------------------------
    # 步骤 4: 从 SQLite 导出数据
    # -----------------------------------------------------------------------
    Write-Log "[Step 4/9] 从 SQLite 导出数据 (dumpdata)" 'Info'

    $env:DB_ENGINE = "django.db.backends.sqlite3"
    $env:DB_NAME = $SqliteDb

    $proc = Start-Process -FilePath "python" `
        -ArgumentList "-m", "django", "dumpdata", "--all", "--indent", "2", "-o", $DumpFile `
        -WorkingDirectory $ProjectRoot `
        -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile

    if ($proc.ExitCode -ne 0) {
        throw "dumpdata 导出失败，退出码: $($proc.ExitCode)"
    }

    if (Test-Path $DumpFile) {
        $size = (Get-Item $DumpFile).Length
        $sizeStr = if ($size -gt 1MB) { "{0:N2} MB" -f ($size / 1MB) } else { "{0:N2} KB" -f ($size / 1KB) }
        Write-Log "导出完成: $DumpFile (大小: $sizeStr)" 'Ok'
    }
    else {
        throw "导出失败，未生成文件"
    }

    # -----------------------------------------------------------------------
    # 步骤 5: 切换配置到 PostgreSQL
    # -----------------------------------------------------------------------
    Write-Log "[Step 5/9] 切换配置到 PostgreSQL" 'Info'

    $env:DB_ENGINE = "postgresql"
    $env:DB_NAME = $PgDb
    $env:DB_USER = $PgUser
    $env:DB_PASSWORD = $PgPassword
    $env:DB_HOST = $PgHost
    $env:DB_PORT = "$PgPort"

    Write-Log "环境变量已设置，Django 将使用 PostgreSQL" 'Ok'

    # -----------------------------------------------------------------------
    # 步骤 6: 执行 migrate 创建表结构
    # -----------------------------------------------------------------------
    Write-Log "[Step 6/9] 执行 migrate 创建表结构" 'Info'

    $proc = Start-Process -FilePath "python" `
        -ArgumentList "-m", "django", "migrate", "--run-syncdb" `
        -WorkingDirectory $ProjectRoot `
        -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile

    if ($proc.ExitCode -ne 0) {
        throw "migrate 失败，退出码: $($proc.ExitCode)"
    }
    Write-Log "PostgreSQL 表结构创建完成" 'Ok'

    # -----------------------------------------------------------------------
    # 步骤 7: 导入数据
    # -----------------------------------------------------------------------
    Write-Log "[Step 7/9] 导入数据到 PostgreSQL" 'Info'

    $BatchScript = Join-Path $ScriptDir "batch_loaddata.py"
    if (Test-Path $BatchScript) {
        Write-Log "使用 batch_loaddata.py 分批导入..." 'Info'
        $proc = Start-Process -FilePath "python" `
            -ArgumentList $BatchScript, $DumpFile, "--batch-size", "50000" `
            -WorkingDirectory $ProjectRoot `
            -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile
    }
    else {
        Write-Log "未找到 batch_loaddata.py，使用原生 loaddata" 'Warn'
        $proc = Start-Process -FilePath "python" `
            -ArgumentList "-m", "django", "loaddata", $DumpFile `
            -WorkingDirectory $ProjectRoot `
            -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile
    }

    if ($proc.ExitCode -ne 0) {
        throw "loaddata 导入失败，退出码: $($proc.ExitCode)"
    }
    Write-Log "数据导入完成" 'Ok'

    # -----------------------------------------------------------------------
    # 步骤 8: 更新 PostgreSQL 序列
    # -----------------------------------------------------------------------
    Write-Log "[Step 8/9] 更新 PostgreSQL 序列" 'Info'

    $SqlSeqFile = Join-Path $BackupDir "sqlsequencereset.sql"
    $proc = Start-Process -FilePath "python" `
        -ArgumentList "-m", "django", "sqlsequencereset", "system", "cmdb", "ai_ops", "script_manager", "k8s_manager", "monitoring" `
        -WorkingDirectory $ProjectRoot `
        -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $SqlSeqFile -RedirectStandardError $LogFile

    if ($proc.ExitCode -ne 0) {
        throw "sqlsequencereset 生成失败，退出码: $($proc.ExitCode)"
    }

    $proc = Start-Process -FilePath "python" `
        -ArgumentList "-m", "django", "dbshell" `
        -WorkingDirectory $ProjectRoot `
        -Wait -PassThru -NoNewWindow `
        -RedirectStandardInput $SqlSeqFile -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile

    if ($proc.ExitCode -ne 0) {
        throw "dbshell 执行序列更新失败，退出码: $($proc.ExitCode)"
    }
    Write-Log "序列更新完成" 'Ok'

    # -----------------------------------------------------------------------
    # 步骤 9: 迁移后验证
    # -----------------------------------------------------------------------
    Write-Log "[Step 9/9] 迁移后验证" 'Info'
    $ValidationScript = Join-Path $ScriptDir "post_migration_validation.py"
    if (Test-Path $ValidationScript) {
        $proc = Start-Process -FilePath "python" -ArgumentList $ValidationScript `
            -WorkingDirectory $ProjectRoot `
            -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile
        if ($proc.ExitCode -ne 0) {
            Write-Log "迁移后验证发现问题，退出码: $($proc.ExitCode)" 'Warn'
        }
        else {
            Write-Log "迁移后验证完成" 'Ok'
        }
    }
    else {
        Write-Log "未找到 post_migration_validation.py，跳过验证" 'Warn'
    }

    # -----------------------------------------------------------------------
    # 启动应用服务（可选）
    # -----------------------------------------------------------------------
    if ($AppService) {
        Write-Log "启动应用服务: $AppService" 'Info'
        try {
            Start-Service -Name $AppService -ErrorAction Stop
            Write-Log "应用服务已启动" 'Ok'
        }
        catch {
            Write-Log "启动应用服务失败: $_ 请手动检查" 'Warn'
        }
    }

    Write-Log "============================================================" 'Info'
    Write-Log "迁移流程全部完成!" 'Ok'
    Write-Log "备份目录: $BackupDir" 'Info'
    Write-Log "============================================================" 'Info'
}
catch {
    Write-Log "迁移流程异常中断: $_" 'Error'
    Write-Log "请检查日志: $LogFile" 'Error'

    if ($AppService) {
        Write-Log "尝试恢复应用服务: $AppService" 'Warn'
        try {
            Start-Service -Name $AppService -ErrorAction Stop
        }
        catch {
            Write-Log "恢复服务失败: $_" 'Warn'
        }
    }

    exit 1
}
