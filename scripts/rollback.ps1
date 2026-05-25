# =============================================================================
# AiOps 数据库迁移回滚脚本 (PowerShell 版本)
# 支持场景:
#   --in-progress    : 迁移过程中回滚
#   --post-migration : 迁移完成后回滚
# =============================================================================

#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$InProgress,

    [Parameter(Mandatory = $false)]
    [switch]$PostMigration,

    [Parameter(Mandatory = $false)]
    [switch]$Help
)

# ---------------------------------------------------------------------------
# 基础配置
# ---------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$BackupDir = Join-Path $ProjectRoot "backups"
$LogDir = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDir ("rollback_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))
$SettingsPath = Join-Path $ProjectRoot "ops_platform\settings.py"
$EnvPath = Join-Path $ProjectRoot ".env"
$SqlitePath = Join-Path $ProjectRoot "db.sqlite3"
$SshLogsDir = Join-Path $ProjectRoot "ssh_logs"

# 颜色配置
$ColorInfo = "Cyan"
$ColorOk = "Green"
$ColorWarn = "Yellow"
$ColorError = "Red"

# ---------------------------------------------------------------------------
# 日志函数
# ---------------------------------------------------------------------------
function Write-LogInfo {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [INFO] $Message"
    Write-Host $line -ForegroundColor $ColorInfo
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

function Write-LogOk {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [OK] $Message"
    Write-Host $line -ForegroundColor $ColorOk
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

function Write-LogWarn {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [WARN] $Message"
    Write-Host $line -ForegroundColor $ColorWarn
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

function Write-LogError {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [ERROR] $Message"
    Write-Host $line -ForegroundColor $ColorError
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# 确认提示
# ---------------------------------------------------------------------------
function Confirm-Action {
    param([string]$Prompt)
    $response = Read-Host "$Prompt [y/N]"
    return ($response -match '^[yY]([eE][sS])?$')
}

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------
function Initialize-Environment {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-LogInfo "========================================"
    Write-LogInfo "AiOps 数据库迁移回滚脚本 (PowerShell)"
    Write-LogInfo "项目目录: $ProjectRoot"
    Write-LogInfo "日志文件: $LogFile"
    Write-LogInfo "========================================"
}

# ---------------------------------------------------------------------------
# 读取 PostgreSQL 配置
# ---------------------------------------------------------------------------
$script:PgHost = "localhost"
$script:PgPort = "5432"
$script:PgUser = "postgres"
$script:PgPassword = ""
$script:PgDb = "aiops_db"

function Load-PgConfig {
    if (Test-Path $EnvPath) {
        Get-Content $EnvPath | ForEach-Object {
            $line = $_.Trim()
            if ($line -match '^#') { return }
            if ([string]::IsNullOrWhiteSpace($line)) { return }
            if ($line -match '^(\w+)\s*=\s*(.*)$') {
                $key = $matches[1]
                $value = $matches[2] -replace '^["'"']|["'"']$'
                switch ($key) {
                    "DB_HOST" { $script:PgHost = $value }
                    "DB_PORT" { $script:PgPort = $value }
                    "DB_USER" { $script:PgUser = $value }
                    "DB_PASSWORD" { $script:PgPassword = $value }
                    "DB_NAME" { $script:PgDb = $value }
                }
            }
        }
    }
    Write-LogInfo "PostgreSQL 配置: $script:PgUser@$script:PgHost`:$script:PgPort/$script:PgDb"
}

# ---------------------------------------------------------------------------
# 服务管理
# ---------------------------------------------------------------------------
function Stop-Services {
    Write-LogInfo "停止 Django/Celery 服务..."

    # 尝试停止 Windows 服务
    $serviceNames = @("aiops-web", "aiops-celery-worker", "aiops-celery-beat")
    foreach ($svc in $serviceNames) {
        $service = Get-Service -Name $svc -ErrorAction SilentlyContinue
        if ($service) {
            Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
            Write-LogInfo "  已停止服务: $svc"
        }
    }

    # 停止常见进程
    $patterns = @("manage.py runserver", "celery -A ops_platform", "daphne", "gunicorn", "python.exe")
    foreach ($pattern in $patterns) {
        $procs = Get-Process | Where-Object { $_.CommandLine -like "*$pattern*" -or $_.Name -like "*$pattern*" } -ErrorAction SilentlyContinue
        if ($procs) {
            foreach ($proc in $procs) {
                Write-LogWarn "发现进程 ($pattern): PID $($proc.Id)"
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Start-Sleep -Seconds 2
    Write-LogOk "应用服务已停止"
}

function Restart-Services {
    Write-LogInfo "重启应用服务..."

    # Windows 服务
    $serviceNames = @("aiops-web", "aiops-celery-worker", "aiops-celery-beat")
    $restarted = $false
    foreach ($svc in $serviceNames) {
        $service = Get-Service -Name $svc -ErrorAction SilentlyContinue
        if ($service) {
            Start-Service -Name $svc -ErrorAction SilentlyContinue
            $restarted = $true
        }
    }
    if ($restarted) {
        Write-LogOk "Windows 服务已重启"
        return
    }

    # docker-compose
    $composeFile = Join-Path $ProjectRoot "docker-compose.yml"
    if (Test-Path $composeFile) {
        if (Confirm-Action "是否使用 docker-compose 重启服务?") {
            try {
                Push-Location $ProjectRoot
                docker-compose restart 2>$null
                Pop-Location
                Write-LogOk "docker-compose 服务已重启"
                return
            }
            catch {
                Write-LogWarn "docker-compose 重启失败"
            }
        }
    }

    Write-LogWarn "未能自动重启服务，请手动启动 Django/Celery"
    Write-LogInfo "提示: python manage.py runserver / celery -A ops_platform worker -l info"
}

# ---------------------------------------------------------------------------
# 场景 A: 迁移过程中回滚
# ---------------------------------------------------------------------------
function Invoke-RollbackInProgress {
    Write-LogInfo "【场景 A】迁移过程中回滚"

    # 1. 停止 loaddata 进程
    Write-LogInfo "步骤 1/6: 检查并停止 loaddata 进程..."
    $loaddataProcs = Get-Process | Where-Object { $_.CommandLine -like "*loaddata*" -or $_.Name -like "*loaddata*" } -ErrorAction SilentlyContinue
    if ($loaddataProcs) {
        Write-LogWarn "发现 loaddata 进程"
        foreach ($proc in $loaddataProcs) {
            Write-LogWarn "  PID: $($proc.Id)"
        }
        if (Confirm-Action "确认终止上述 loaddata 进程?") {
            foreach ($proc in $loaddataProcs) {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 2
            Write-LogOk "loaddata 进程已终止"
        }
        else {
            Write-LogWarn "跳过终止 loaddata"
        }
    }
    else {
        Write-LogInfo "未运行中的 loaddata 进程"
    }

    # 2. 清理 PostgreSQL 不完整数据
    Write-LogInfo "步骤 2/6: 清理 PostgreSQL 不完整数据..."
    if (Confirm-Action "即将执行 DROP SCHEMA public CASCADE; 这将清空 PostgreSQL 所有数据! 确认?") {
        $env:PGPASSWORD = $script:PgPassword
        try {
            $output = psql -h $script:PgHost -p $script:PgPort -U $script:PgUser -d $script:PgDb -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-LogOk "PostgreSQL Schema 已清理并重建"
            }
            else {
                Write-LogWarn "Schema 清理失败或数据库不存在 (非致命): $output"
            }
        }
        catch {
            Write-LogWarn "psql 执行异常 (非致命): $_"
        }
        finally {
            Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        }
    }
    else {
        Write-LogWarn "跳过 PostgreSQL 清理"
    }

    # 3. 恢复 settings.py / 环境变量指向 SQLite
    Write-LogInfo "步骤 3/6: 恢复配置指向 SQLite..."
    if (Test-Path $SettingsPath) {
        $settingsBackup = Get-ChildItem -Path $BackupDir -Filter "settings.py.pre_migration" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($settingsBackup) {
            Copy-Item -Path $settingsBackup.FullName -Destination $SettingsPath -Force
            Write-LogOk "settings.py 已从备份恢复: $($settingsBackup.FullName)"
        }
        else {
            if (Test-Path $EnvPath) {
                (Get-Content $EnvPath) -replace '^DB_ENGINE=.*', 'DB_ENGINE=' | Set-Content $EnvPath -Encoding UTF8
                Write-LogOk ".env 中 DB_ENGINE 已清空 (恢复 SQLite)"
            }
            Write-LogWarn "未找到 settings.py 备份，请手动确认 DATABASES 配置"
        }
    }

    # 4. 验证 SQLite 数据完好
    Write-LogInfo "步骤 4/6: 验证 SQLite 数据完好..."
    if (Test-Path $SqlitePath) {
        try {
            $integrity = sqlite3 $SqlitePath "PRAGMA integrity_check;" 2>$null
            if ($integrity -eq "ok") {
                $count = sqlite3 $SqlitePath "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>$null
                Write-LogOk "SQLite 完整性检查通过 (表数量: $count)"
            }
            else {
                Write-LogError "SQLite 完整性检查失败!"
                if (-not (Confirm-Action "SQLite 可能损坏，是否继续?")) {
                    exit 1
                }
            }
        }
        catch {
            Write-LogError "SQLite 检查异常: $_"
        }
    }
    else {
        Write-LogWarn "SQLite 文件不存在: $SqlitePath"
        $sqliteBackup = Get-ChildItem -Path $BackupDir -Filter "db.sqlite3.backup" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($sqliteBackup) {
            if (Confirm-Action "找到 SQLite 备份 $($sqliteBackup.FullName)，是否恢复?") {
                Copy-Item -Path $sqliteBackup.FullName -Destination $SqlitePath -Force
                Write-LogOk "SQLite 已从备份恢复"
            }
        }
    }

    # 5. 恢复 SSH 日志目录
    Write-LogInfo "步骤 5/6: 检查 SSH 日志目录..."
    if (Test-Path $SshLogsDir) {
        Write-LogOk "SSH 日志目录存在: $SshLogsDir"
    }
    else {
        Write-LogWarn "SSH 日志目录不存在，尝试从备份恢复..."
        $sshBackup = Get-ChildItem -Path $BackupDir -Directory -Filter "ssh_logs*" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($sshBackup) {
            if (Confirm-Action "找到 SSH 日志备份，是否恢复?") {
                Copy-Item -Path $sshBackup.FullName -Destination $SshLogsDir -Recurse -Force
                Write-LogOk "SSH 日志已恢复"
            }
        }
    }

    # 6. 重启应用服务
    Write-LogInfo "步骤 6/6: 重启应用服务..."
    Restart-Services

    Write-LogOk "【场景 A】迁移过程中回滚完成!"
}

# ---------------------------------------------------------------------------
# 场景 B: 迁移完成后回滚
# ---------------------------------------------------------------------------
function Invoke-RollbackPostMigration {
    Write-LogInfo "【场景 B】迁移完成后回滚"

    # 1. 备份当前 PostgreSQL 数据
    Write-LogInfo "步骤 1/7: 备份当前 PostgreSQL 数据..."
    $pgDumpFile = Join-Path $BackupDir ("pg_pre_rollback_{0:yyyyMMdd_HHmmss}.sql" -f (Get-Date))
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    if (Confirm-Action "是否备份当前 PostgreSQL 数据到 $pgDumpFile?") {
        $env:PGPASSWORD = $script:PgPassword
        try {
            pg_dump -h $script:PgHost -p $script:PgPort -U $script:PgUser -d $script:PgDb --no-owner --no-privileges > $pgDumpFile 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Path $pgDumpFile)) {
                $size = (Get-Item $pgDumpFile).Length
                $sizeMb = [math]::Round($size / 1MB, 2)
                Write-LogOk "PostgreSQL 备份完成 (${sizeMb}MB): $pgDumpFile"
            }
            else {
                Write-LogWarn "pg_dump 失败 (非致命，继续回滚)"
            }
        }
        catch {
            Write-LogWarn "pg_dump 异常 (非致命): $_"
        }
        finally {
            Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        }
    }
    else {
        Write-LogWarn "跳过 PostgreSQL 备份"
    }

    # 2. 停止所有应用服务
    Write-LogInfo "步骤 2/7: 停止所有应用服务..."
    Stop-Services

    # 3. 从备份恢复 SQLite 文件
    Write-LogInfo "步骤 3/7: 从备份恢复 SQLite 文件..."
    $sqliteBackup = Get-ChildItem -Path $BackupDir -Filter "db.sqlite3.backup" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($sqliteBackup) {
        if (Confirm-Action "确认从备份恢复 SQLite? 源: $($sqliteBackup.FullName) → 目标: $SqlitePath") {
            Copy-Item -Path $sqliteBackup.FullName -Destination $SqlitePath -Force
            Write-LogOk "SQLite 文件已恢复"
        }
        else {
            Write-LogError "用户取消恢复 SQLite"
            exit 1
        }
    }
    else {
        Write-LogError "未找到 SQLite 备份文件 (db.sqlite3.backup)"
        Write-LogInfo "备份目录内容:"
        Get-ChildItem -Path $BackupDir -ErrorAction SilentlyContinue | ForEach-Object { Write-LogInfo "  $($_.Name)" }
        if (-not (Confirm-Action "未找到备份，是否继续?")) {
            exit 1
        }
    }

    # 4. 恢复 SSH 日志目录
    Write-LogInfo "步骤 4/7: 恢复 SSH 日志目录..."
    $sshBackup = Get-ChildItem -Path $BackupDir -Directory -Filter "ssh_logs*" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($sshBackup) {
        if (Confirm-Action "找到 SSH 日志备份 $($sshBackup.FullName)，是否恢复?") {
            if (Test-Path $SshLogsDir) {
                Remove-Item -Path $SshLogsDir -Recurse -Force
            }
            Copy-Item -Path $sshBackup.FullName -Destination $SshLogsDir -Recurse -Force
            Write-LogOk "SSH 日志目录已恢复"
        }
    }
    else {
        Write-LogInfo "未找到 SSH 日志备份，跳过"
    }

    # 5. 切换配置回 SQLite
    Write-LogInfo "步骤 5/7: 切换配置回 SQLite..."
    $settingsBackup = Get-ChildItem -Path $BackupDir -Filter "settings.py.pre_migration" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($settingsBackup) {
        Copy-Item -Path $settingsBackup.FullName -Destination $SettingsPath -Force
        Write-LogOk "settings.py 已从备份恢复"
    }
    else {
        Write-LogWarn "未找到 settings.py 备份"
    }

    if (Test-Path $EnvPath) {
        (Get-Content $EnvPath) -replace '^DB_ENGINE=.*', 'DB_ENGINE=' | Set-Content $EnvPath -Encoding UTF8
        Write-LogOk ".env 中 DB_ENGINE 已清空 (恢复 SQLite)"
    }

    # 6. 验证 SQLite 数据
    Write-LogInfo "步骤 6/7: 验证 SQLite 数据..."
    if (Test-Path $SqlitePath) {
        try {
            $integrity = sqlite3 $SqlitePath "PRAGMA integrity_check;" 2>$null
            if ($integrity -eq "ok") {
                $count = sqlite3 $SqlitePath "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>$null
                Write-LogOk "SQLite 验证通过 (表数量: $count)"
            }
            else {
                Write-LogError "SQLite 验证失败!"
                exit 1
            }
        }
        catch {
            Write-LogError "SQLite 验证异常: $_"
            exit 1
        }
    }
    else {
        Write-LogError "SQLite 文件恢复后仍不存在!"
        exit 1
    }

    # 7. 重启服务
    Write-LogInfo "步骤 7/7: 重启应用服务..."
    Restart-Services

    Write-LogOk "【场景 B】迁移完成后回滚完成!"
}

# ---------------------------------------------------------------------------
# 用法提示
# ---------------------------------------------------------------------------
function Show-Usage {
    $scriptName = Split-Path -Leaf $MyInvocation.MyCommand.Definition
    Write-Host @"
用法: .\$scriptName [选项]

选项:
    -InProgress       场景 A: 迁移过程中回滚
    -PostMigration    场景 B: 迁移完成后回滚
    -Help             显示此帮助

示例:
    .\$scriptName -InProgress
    .\$scriptName -PostMigration
"@
}

# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
function Main {
    Initialize-Environment
    Load-PgConfig

    if ($Help) {
        Show-Usage
        exit 0
    }

    if ($InProgress) {
        if (Confirm-Action "即将执行【场景 A: 迁移过程中回滚】，确认?") {
            Invoke-RollbackInProgress
        }
        else {
            Write-LogInfo "已取消"
            exit 0
        }
    }
    elseif ($PostMigration) {
        if (Confirm-Action "即将执行【场景 B: 迁移完成后回滚】，确认?") {
            Invoke-RollbackPostMigration
        }
        else {
            Write-LogInfo "已取消"
            exit 0
        }
    }
    else {
        Show-Usage
        exit 1
    }
}

Main
