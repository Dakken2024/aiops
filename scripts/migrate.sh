#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# =============================================================================
# AiOps SQLite → PostgreSQL 一键迁移脚本 (Bash 版本)
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

set -euo pipefail

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_ROOT/backups/$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$BACKUP_DIR/migration.log"
DUMP_FILE="$BACKUP_DIR/dumpdata.json"
SETTINGS_MODULE="ops_platform.settings"

# Django 环境变量
export DJANGO_SETTINGS_MODULE="$SETTINGS_MODULE"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

# PostgreSQL 配置（可通过环境变量覆盖）
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-postgres}"
PG_PASSWORD="${PG_PASSWORD:-}"
PG_DB="${PG_DB:-aiops_db}"

# 可选：停止/启动的服务名（systemd）
APP_SERVICE="${APP_SERVICE:-}"

# ---------------------------------------------------------------------------
# 颜色输出
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC}  $1" | tee -a "$LOG_FILE"
}

log_ok() {
    echo -e "${GREEN}[OK]${NC}   $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC}  $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------
cleanup_on_error() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "迁移流程异常中断 (退出码: $exit_code)"
        log_error "请检查日志: $LOG_FILE"
        if [[ -n "${APP_SERVICE:-}" ]]; then
            log_warn "尝试恢复应用服务: $APP_SERVICE"
            sudo systemctl start "$APP_SERVICE" 2>/dev/null || true
        fi
    fi
}
trap cleanup_on_error EXIT

# ---------------------------------------------------------------------------
# 步骤函数
# ---------------------------------------------------------------------------

step_stop_app() {
    if [[ -z "$APP_SERVICE" ]]; then
        log_info "跳过停止应用服务（未配置 APP_SERVICE）"
        return 0
    fi

    log_info "[Step 1/9] 停止应用服务: $APP_SERVICE"
    if sudo systemctl stop "$APP_SERVICE" 2>/dev/null; then
        log_ok "应用服务已停止"
    else
        log_warn "停止应用服务失败，继续执行..."
    fi
}

step_backup() {
    log_info "[Step 2/9] 备份 SQLite 数据库"
    mkdir -p "$BACKUP_DIR"

    local sqlite_db="$PROJECT_ROOT/db.sqlite3"
    if [[ -f "$sqlite_db" ]]; then
        cp "$sqlite_db" "$BACKUP_DIR/db.sqlite3.bak"
        log_ok "SQLite 备份完成: $BACKUP_DIR/db.sqlite3.bak"
    else
        log_warn "未找到 db.sqlite3，跳过备份"
    fi

    # 同时备份 settings.py
    local settings_file="$PROJECT_ROOT/ops_platform/settings.py"
    if [[ -f "$settings_file" ]]; then
        cp "$settings_file" "$BACKUP_DIR/settings.py.bak"
        log_ok "settings.py 备份完成"
    fi
}

step_cleanup() {
    log_info "[Step 3/9] 运行迁移前数据清洗"
    local cleanup_script="$SCRIPT_DIR/pre_migration_cleanup.py"
    if [[ ! -f "$cleanup_script" ]]; then
        log_error "未找到清洗脚本: $cleanup_script"
        return 1
    fi

    if python "$cleanup_script" >> "$LOG_FILE" 2>&1; then
        log_ok "数据清洗完成"
    else
        log_error "数据清洗失败，请检查日志"
        return 1
    fi
}

step_dumpdata() {
    log_info "[Step 4/9] 从 SQLite 导出数据 (dumpdata)"
    cd "$PROJECT_ROOT"

    # 确保使用 SQLite 配置导出
    DB_ENGINE="django.db.backends.sqlite3" \
    DB_NAME="$PROJECT_ROOT/db.sqlite3" \
    python -m django dumpdata --all --indent 2 -o "$DUMP_FILE" 2>>"$LOG_FILE"

    if [[ -f "$DUMP_FILE" ]]; then
        local size
        size=$(du -h "$DUMP_FILE" | cut -f1)
        log_ok "导出完成: $DUMP_FILE (大小: $size)"
    else
        log_error "导出失败，未生成文件"
        return 1
    fi
}

step_switch_config() {
    log_info "[Step 5/9] 切换配置到 PostgreSQL"
    local settings_file="$PROJECT_ROOT/ops_platform/settings.py"

    if [[ ! -f "$settings_file" ]]; then
        log_error "未找到 settings.py"
        return 1
    fi

    # 使用 sed 切换默认数据库引擎注释（根据项目 settings.py 的实际情况）
    # 这里通过设置环境变量 DB_ENGINE=postgresql 让 Django 自动切换
    export DB_ENGINE="postgresql"
    export DB_NAME="$PG_DB"
    export DB_USER="$PG_USER"
    export DB_PASSWORD="$PG_PASSWORD"
    export DB_HOST="$PG_HOST"
    export DB_PORT="$PG_PORT"

    log_ok "环境变量已设置，Django 将使用 PostgreSQL"
}

step_migrate() {
    log_info "[Step 6/9] 执行 migrate 创建表结构"
    cd "$PROJECT_ROOT"

    # 确保使用 PostgreSQL
    DB_ENGINE="postgresql" \
    DB_NAME="$PG_DB" \
    DB_USER="$PG_USER" \
    DB_PASSWORD="$PG_PASSWORD" \
    DB_HOST="$PG_HOST" \
    DB_PORT="$PG_PORT" \
    python -m django migrate --run-syncdb 2>>"$LOG_FILE"

    log_ok "PostgreSQL 表结构创建完成"
}

step_loaddata() {
    log_info "[Step 7/9] 导入数据到 PostgreSQL"
    cd "$PROJECT_ROOT"

    if [[ ! -f "$DUMP_FILE" ]]; then
        log_error "未找到导出文件: $DUMP_FILE"
        return 1
    fi

    # 优先使用 batch_loaddata.py 分批导入
    local batch_script="$SCRIPT_DIR/batch_loaddata.py"
    if [[ -f "$batch_script" ]]; then
        log_info "使用 batch_loaddata.py 分批导入..."
        DB_ENGINE="postgresql" \
        DB_NAME="$PG_DB" \
        DB_USER="$PG_USER" \
        DB_PASSWORD="$PG_PASSWORD" \
        DB_HOST="$PG_HOST" \
        DB_PORT="$PG_PORT" \
        python "$batch_script" "$DUMP_FILE" --batch-size 50000 2>>"$LOG_FILE"
    else
        log_warn "未找到 batch_loaddata.py，使用原生 loaddata"
        DB_ENGINE="postgresql" \
        DB_NAME="$PG_DB" \
        DB_USER="$PG_USER" \
        DB_PASSWORD="$PG_PASSWORD" \
        DB_HOST="$PG_HOST" \
        DB_PORT="$PG_PORT" \
        python -m django loaddata "$DUMP_FILE" 2>>"$LOG_FILE"
    fi

    log_ok "数据导入完成"
}

step_sqlsequencereset() {
    log_info "[Step 8/9] 更新 PostgreSQL 序列"
    cd "$PROJECT_ROOT"

    DB_ENGINE="postgresql" \
    DB_NAME="$PG_DB" \
    DB_USER="$PG_USER" \
    DB_PASSWORD="$PG_PASSWORD" \
    DB_HOST="$PG_HOST" \
    DB_PORT="$PG_PORT" \
    python -m django sqlsequencereset system cmdb ai_ops script_manager k8s_manager monitoring 2>>"$LOG_FILE" | \
    DB_ENGINE="postgresql" \
    DB_NAME="$PG_DB" \
    DB_USER="$PG_USER" \
    DB_PASSWORD="$PG_PASSWORD" \
    DB_HOST="$PG_HOST" \
    DB_PORT="$PG_PORT" \
    python -m django dbshell 2>>"$LOG_FILE"

    log_ok "序列更新完成"
}

step_post_validation() {
    log_info "[Step 9/9] 迁移后验证"
    local validation_script="$SCRIPT_DIR/post_migration_validation.py"
    if [[ -f "$validation_script" ]]; then
        DB_ENGINE="postgresql" \
        DB_NAME="$PG_DB" \
        DB_USER="$PG_USER" \
        DB_PASSWORD="$PG_PASSWORD" \
        DB_HOST="$PG_HOST" \
        DB_PORT="$PG_PORT" \
        python "$validation_script" >> "$LOG_FILE" 2>&1
        log_ok "迁移后验证完成"
    else
        log_warn "未找到 post_migration_validation.py，跳过验证"
    fi
}

step_start_app() {
    if [[ -z "$APP_SERVICE" ]]; then
        return 0
    fi

    log_info "启动应用服务: $APP_SERVICE"
    if sudo systemctl start "$APP_SERVICE" 2>/dev/null; then
        log_ok "应用服务已启动"
    else
        log_warn "启动应用服务失败，请手动检查"
    fi
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
main() {
    log_info "============================================================"
    log_info "AiOps 数据库迁移: SQLite → PostgreSQL"
    log_info "目标: postgresql://${PG_USER}@${PG_HOST}:${PG_PORT}/${PG_DB}"
    log_info "日志: $LOG_FILE"
    log_info "============================================================"

    mkdir -p "$BACKUP_DIR"

    step_stop_app
    step_backup
    step_cleanup
    step_dumpdata
    step_switch_config
    step_migrate
    step_loaddata
    step_sqlsequencereset
    step_post_validation
    step_start_app

    log_info "============================================================"
    log_ok "迁移流程全部完成!"
    log_info "备份目录: $BACKUP_DIR"
    log_info "============================================================"
}

# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pg-host)
            PG_HOST="$2"
            shift 2
            ;;
        --pg-port)
            PG_PORT="$2"
            shift 2
            ;;
        --pg-user)
            PG_USER="$2"
            shift 2
            ;;
        --pg-password)
            PG_PASSWORD="$2"
            shift 2
            ;;
        --pg-db)
            PG_DB="$2"
            shift 2
            ;;
        --app-service)
            APP_SERVICE="$2"
            shift 2
            ;;
        --skip-backup)
            SKIP_BACKUP=1
            shift
            ;;
        -h|--help)
            cat <<EOF
用法: $0 [选项]

选项:
  --pg-host HOST       PostgreSQL 主机 (默认: localhost)
  --pg-port PORT       PostgreSQL 端口 (默认: 5432)
  --pg-user USER       PostgreSQL 用户 (默认: postgres)
  --pg-password PASS   PostgreSQL 密码 (默认: 空)
  --pg-db DBNAME       PostgreSQL 数据库名 (默认: aiops_db)
  --app-service NAME   要停止/启动的 systemd 服务名
  --skip-backup        跳过备份（危险！）
  -h, --help           显示此帮助

环境变量:
  PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DB, APP_SERVICE

示例:
  $0 --pg-host 192.168.1.100 --pg-db aiops_prod
EOF
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            exit 1
            ;;
    esac
done

main
