#!/usr/bin/env bash
# =============================================================================
# AiOps 数据库迁移回滚脚本 (Bash 版本)
# 支持场景:
#   --in-progress   : 迁移过程中回滚
#   --post-migration: 迁移完成后回滚
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 基础配置
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_ROOT/backups"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/rollback_$(date +%Y%m%d_%H%M%S).log"
SETTINGS_PATH="$PROJECT_ROOT/ops_platform/settings.py"
ENV_PATH="$PROJECT_ROOT/.env"
SQLITE_PATH="$PROJECT_ROOT/db.sqlite3"
SSH_LOGS_DIR="$PROJECT_ROOT/ssh_logs"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# 日志函数
# ---------------------------------------------------------------------------
log_info() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $1"
    echo -e "${BLUE}$msg${NC}"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

log_ok() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [OK] $1"
    echo -e "${GREEN}$msg${NC}"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

log_warn() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $1"
    echo -e "${YELLOW}$msg${NC}"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

log_error() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1"
    echo -e "${RED}$msg${NC}"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# 确认提示
# ---------------------------------------------------------------------------
confirm() {
    local prompt="$1"
    read -r -p "$prompt [y/N]: " response
    case "$response" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------
init() {
    mkdir -p "$LOG_DIR"
    log_info "========================================"
    log_info "AiOps 数据库迁移回滚脚本"
    log_info "项目目录: $PROJECT_ROOT"
    log_info "日志文件: $LOG_FILE"
    log_info "========================================"
}

# ---------------------------------------------------------------------------
# 读取 .env 中的 PostgreSQL 配置
# ---------------------------------------------------------------------------
load_pg_config() {
    PG_HOST="localhost"
    PG_PORT="5432"
    PG_USER="postgres"
    PG_PASSWORD=""
    PG_DB="aiops_db"

    if [[ -f "$ENV_PATH" ]]; then
        while IFS='=' read -r key value; do
            [[ "$key" =~ ^#.*$ ]] && continue
            [[ -z "$key" ]] && continue
            value="$(echo "$value" | sed 's/^["'\''"]//;s/["'\''"]$//')"
            case "$key" in
                DB_HOST) PG_HOST="$value" ;;
                DB_PORT) PG_PORT="$value" ;;
                DB_USER) PG_USER="$value" ;;
                DB_PASSWORD) PG_PASSWORD="$value" ;;
                DB_NAME) PG_DB="$value" ;;
            esac
        done < "$ENV_PATH"
    fi

    log_info "PostgreSQL 配置: $PG_USER@$PG_HOST:$PG_PORT/$PG_DB"
}

# ---------------------------------------------------------------------------
# 场景 A: 迁移过程中回滚
# ---------------------------------------------------------------------------
rollback_in_progress() {
    log_info "【场景 A】迁移过程中回滚"

    # 1. 停止 loaddata 进程
    log_info "步骤 1/6: 检查并停止 loaddata 进程..."
    local pids
    pids=$(pgrep -f "loaddata" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        log_warn "发现 loaddata 进程: $pids"
        if confirm "确认终止上述 loaddata 进程?"; then
            echo "$pids" | xargs kill -TERM 2>/dev/null || true
            sleep 2
            # 强制清理残留
            local residual
            residual=$(pgrep -f "loaddata" 2>/dev/null || true)
            if [[ -n "$residual" ]]; then
                echo "$residual" | xargs kill -KILL 2>/dev/null || true
            fi
            log_ok "loaddata 进程已终止"
        else
            log_warn "跳过终止 loaddata"
        fi
    else
        log_info "未运行中的 loaddata 进程"
    fi

    # 2. 清理 PostgreSQL 不完整数据
    log_info "步骤 2/6: 清理 PostgreSQL 不完整数据..."
    if confirm "⚠️  即将执行 DROP SCHEMA public CASCADE; 这将清空 PostgreSQL 所有数据! 确认?"; then
        export PGPASSWORD="$PG_PASSWORD"
        if psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" 2>/dev/null; then
            log_ok "PostgreSQL Schema 已清理并重建"
        else
            log_warn "Schema 清理失败或数据库不存在 (非致命)"
        fi
        unset PGPASSWORD
    else
        log_warn "跳过 PostgreSQL 清理"
    fi

    # 3. 恢复 settings.py / 环境变量指向 SQLite
    log_info "步骤 3/6: 恢复配置指向 SQLite..."
    if [[ -f "$SETTINGS_PATH" ]]; then
        # 优先从备份恢复
        local settings_backup
        settings_backup="$(find "$BACKUP_DIR" -name "settings.py.pre_migration" -print -quit 2>/dev/null || true)"
        if [[ -n "$settings_backup" && -f "$settings_backup" ]]; then
            cp "$settings_backup" "$SETTINGS_PATH"
            log_ok "settings.py 已从备份恢复: $settings_backup"
        else
            # 修改环境变量
            if [[ -f "$ENV_PATH" ]]; then
                sed -i 's/^DB_ENGINE=.*/DB_ENGINE=/' "$ENV_PATH" 2>/dev/null || true
                log_ok ".env 中 DB_ENGINE 已清空 (恢复 SQLite)"
            fi
            log_warn "未找到 settings.py 备份，请手动确认 DATABASES 配置"
        fi
    fi

    # 4. 验证 SQLite 数据完好
    log_info "步骤 4/6: 验证 SQLite 数据完好..."
    if [[ -f "$SQLITE_PATH" ]]; then
        if sqlite3 "$SQLITE_PATH" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
            local count
            count=$(sqlite3 "$SQLITE_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "0")
            log_ok "SQLite 完整性检查通过 (表数量: $count)"
        else
            log_error "SQLite 完整性检查失败!"
            if ! confirm "SQLite 可能损坏，是否继续?"; then
                exit 1
            fi
        fi
    else
        log_warn "SQLite 文件不存在: $SQLITE_PATH"
        # 尝试从备份恢复
        local sqlite_backup
        sqlite_backup="$(find "$BACKUP_DIR" -name "db.sqlite3.backup" -print -quit 2>/dev/null || true)"
        if [[ -n "$sqlite_backup" && -f "$sqlite_backup" ]]; then
            if confirm "找到 SQLite 备份 $sqlite_backup，是否恢复?"; then
                cp "$sqlite_backup" "$SQLITE_PATH"
                log_ok "SQLite 已从备份恢复"
            fi
        fi
    fi

    # 5. 恢复 SSH 日志目录（如有变更）
    log_info "步骤 5/6: 检查 SSH 日志目录..."
    if [[ -d "$SSH_LOGS_DIR" ]]; then
        log_ok "SSH 日志目录存在: $SSH_LOGS_DIR"
    else
        log_warn "SSH 日志目录不存在，尝试从备份恢复..."
        local ssh_backup
        ssh_backup="$(find "$BACKUP_DIR" -type d -name "ssh_logs*" -print -quit 2>/dev/null || true)"
        if [[ -n "$ssh_backup" && -d "$ssh_backup" ]]; then
            if confirm "找到 SSH 日志备份，是否恢复?"; then
                cp -r "$ssh_backup" "$SSH_LOGS_DIR"
                log_ok "SSH 日志已恢复"
            fi
        fi
    fi

    # 6. 重启应用服务
    log_info "步骤 6/6: 重启应用服务..."
    restart_services

    log_ok "【场景 A】迁移过程中回滚完成!"
}

# ---------------------------------------------------------------------------
# 场景 B: 迁移完成后回滚
# ---------------------------------------------------------------------------
rollback_post_migration() {
    log_info "【场景 B】迁移完成后回滚"

    # 1. 备份当前 PostgreSQL 数据
    log_info "步骤 1/7: 备份当前 PostgreSQL 数据..."
    local pg_dump_file="$BACKUP_DIR/pg_pre_rollback_$(date +%Y%m%d_%H%M%S).sql"
    mkdir -p "$BACKUP_DIR"
    if confirm "是否备份当前 PostgreSQL 数据到 $pg_dump_file?"; then
        export PGPASSWORD="$PG_PASSWORD"
        if pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" --no-owner --no-privileges > "$pg_dump_file" 2>/dev/null; then
            local size
            size=$(du -h "$pg_dump_file" 2>/dev/null | cut -f1)
            log_ok "PostgreSQL 备份完成 ($size): $pg_dump_file"
        else
            log_warn "pg_dump 失败 (非致命，继续回滚)"
        fi
        unset PGPASSWORD
    else
        log_warn "跳过 PostgreSQL 备份"
    fi

    # 2. 停止所有应用服务
    log_info "步骤 2/7: 停止所有应用服务..."
    stop_services

    # 3. 从备份恢复 SQLite 文件
    log_info "步骤 3/7: 从备份恢复 SQLite 文件..."
    local sqlite_backup
    sqlite_backup="$(find "$BACKUP_DIR" -name "db.sqlite3.backup" -print -quit 2>/dev/null || true)"
    if [[ -n "$sqlite_backup" && -f "$sqlite_backup" ]]; then
        if confirm "确认从备份恢复 SQLite? 源: $sqlite_backup → 目标: $SQLITE_PATH"; then
            cp "$sqlite_backup" "$SQLITE_PATH"
            log_ok "SQLite 文件已恢复"
        else
            log_error "用户取消恢复 SQLite"
            exit 1
        fi
    else
        log_error "未找到 SQLite 备份文件 (db.sqlite3.backup)"
        log_info "备份目录内容:"
        ls -la "$BACKUP_DIR" 2>/dev/null || true
        if ! confirm "未找到备份，是否继续?"; then
            exit 1
        fi
    fi

    # 4. 恢复 SSH 日志目录
    log_info "步骤 4/7: 恢复 SSH 日志目录..."
    local ssh_backup
    ssh_backup="$(find "$BACKUP_DIR" -type d -name "ssh_logs*" -print -quit 2>/dev/null || true)"
    if [[ -n "$ssh_backup" && -d "$ssh_backup" ]]; then
        if confirm "找到 SSH 日志备份 $ssh_backup，是否恢复?"; then
            rm -rf "$SSH_LOGS_DIR"
            cp -r "$ssh_backup" "$SSH_LOGS_DIR"
            log_ok "SSH 日志目录已恢复"
        fi
    else
        log_info "未找到 SSH 日志备份，跳过"
    fi

    # 5. 切换配置回 SQLite
    log_info "步骤 5/7: 切换配置回 SQLite..."
    local settings_backup
    settings_backup="$(find "$BACKUP_DIR" -name "settings.py.pre_migration" -print -quit 2>/dev/null || true)"
    if [[ -n "$settings_backup" && -f "$settings_backup" ]]; then
        cp "$settings_backup" "$SETTINGS_PATH"
        log_ok "settings.py 已从备份恢复"
    else
        log_warn "未找到 settings.py 备份"
    fi

    if [[ -f "$ENV_PATH" ]]; then
        sed -i 's/^DB_ENGINE=.*/DB_ENGINE=/' "$ENV_PATH" 2>/dev/null || true
        log_ok ".env 中 DB_ENGINE 已清空 (恢复 SQLite)"
    fi

    # 6. 验证 SQLite 数据
    log_info "步骤 6/7: 验证 SQLite 数据..."
    if [[ -f "$SQLITE_PATH" ]]; then
        if sqlite3 "$SQLITE_PATH" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
            local count
            count=$(sqlite3 "$SQLITE_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "0")
            log_ok "SQLite 验证通过 (表数量: $count)"
        else
            log_error "SQLite 验证失败!"
            exit 1
        fi
    else
        log_error "SQLite 文件恢复后仍不存在!"
        exit 1
    fi

    # 7. 重启服务
    log_info "步骤 7/7: 重启应用服务..."
    restart_services

    log_ok "【场景 B】迁移完成后回滚完成!"
}

# ---------------------------------------------------------------------------
# 服务管理
# ---------------------------------------------------------------------------
stop_services() {
    log_info "停止 Django/Celery 服务..."

    # 尝试停止 supervisord / systemd 服务
    if command -v systemctl &>/dev/null; then
        sudo systemctl stop aiops-web aiops-celery-worker aiops-celery-beat 2>/dev/null || true
    fi

    # 停止常见进程名
    local patterns=("manage.py runserver" "celery -A ops_platform" "daphne" "gunicorn")
    for pattern in "${patterns[@]}"; do
        local pids
        pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            log_warn "发现进程 ($pattern): $pids"
            echo "$pids" | xargs kill -TERM 2>/dev/null || true
        fi
    done

    sleep 2

    # 强制清理
    for pattern in "${patterns[@]}"; do
        local residual
        residual=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [[ -n "$residual" ]]; then
            echo "$residual" | xargs kill -KILL 2>/dev/null || true
        fi
    done

    log_ok "应用服务已停止"
}

restart_services() {
    log_info "重启应用服务..."

    # systemd
    if command -v systemctl &>/dev/null; then
        sudo systemctl restart aiops-web aiops-celery-worker aiops-celery-beat 2>/dev/null && {
            log_ok "systemd 服务已重启"
            return 0
        }
    fi

    # supervisord
    if command -v supervisorctl &>/dev/null; then
        supervisorctl restart all 2>/dev/null && {
            log_ok "supervisord 服务已重启"
            return 0
        }
    fi

    # docker-compose
    if [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
        if confirm "是否使用 docker-compose 重启服务?"; then
            (cd "$PROJECT_ROOT" && docker-compose restart) 2>/dev/null && {
                log_ok "docker-compose 服务已重启"
                return 0
            }
        fi
    fi

    log_warn "未能自动重启服务，请手动启动 Django/Celery"
    log_info "提示: python manage.py runserver / celery -A ops_platform worker -l info"
}

# ---------------------------------------------------------------------------
# 用法提示
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
用法: $(basename "$0") [选项]

选项:
    --in-progress      场景 A: 迁移过程中回滚
    --post-migration   场景 B: 迁移完成后回滚
    -h, --help         显示此帮助

示例:
    $(basename "$0") --in-progress
    $(basename "$0") --post-migration
EOF
}

# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
main() {
    init
    load_pg_config

    if [[ $# -eq 0 ]]; then
        usage
        exit 1
    fi

    case "$1" in
        --in-progress)
            if confirm "即将执行【场景 A: 迁移过程中回滚】，确认?"; then
                rollback_in_progress
            else
                log_info "已取消"
                exit 0
            fi
            ;;
        --post-migration)
            if confirm "即将执行【场景 B: 迁移完成后回滚】，确认?"; then
                rollback_post_migration
            else
                log_info "已取消"
                exit 0
            fi
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            usage
            exit 1
            ;;
    esac
}

main "$@"
