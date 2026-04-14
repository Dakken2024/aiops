# -*- coding: utf-8 -*-
"""
Django settings.py 更新模块
将 DATABASES 配置从 SQLite 切换到 PostgreSQL
自动备份原文件，支持回滚
"""

import os
import shutil
import re
import logging

log = logging.getLogger('Migrate.Settings')


def update_settings_for_postgres(settings_path, pg_config, backup_dir):
    """
    修改 settings.py 的 DATABASES 配置指向 PostgreSQL
    pg_config: dict with host, port, user, password, db_name
    """
    if not os.path.exists(settings_path):
        log.error(f"settings.py 不存在: {settings_path}")
        return False

    backup_path = os.path.join(backup_dir, 'settings.py.pre_migration')
    shutil.copy2(settings_path, backup_path)
    log.info(f"  原文件已备份到: {backup_path}")

    with open(settings_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_db_config = f"""DATABASES = {{
        'default': {{
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': '{pg_config['db_name']}',
            'USER': '{pg_config['user']}',
            'PASSWORD': '{pg_config['password']}',
            'HOST': '{pg_config['host']}',
            'PORT': {pg_config['port']},

            'OPTIONS': {{
                'options': '-c statement_timeout=30000 -c lock_timeout=5000'
            }},

            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
        }}
    }}

# === SQLite 回退配置 (如需切回请取消下方注释) ===
# DATABASES = {{
#     'default': {{
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }}
# }}"""

    pattern = r'DATABASES\s*=\s*\{[^}]+\}[^}]*\}'

    if re.search(pattern, content, re.DOTALL):
        new_content = re.sub(pattern, new_db_config, content, count=1)
    else:
        fallback_marker = "# === 4. Channels 配置"
        if fallback_marker in content:
            new_content = content.replace(fallback_marker, f"{new_db_config}\n\n{fallback_marker}")
        else:
            log.error("无法找到替换位置")
            return False

    with open(settings_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    log.info("  ✅ settings.py 已更新为 PostgreSQL 配置")
    return True


def rollback_settings(settings_path, backup_dir):
    """回滚 settings.py 到迁移前版本"""
    backup_path = os.path.join(backup_dir, 'settings.py.pre_migration')
    if not os.path.exists(backup_path):
        log.error(f"备份文件不存在: {backup_path}")
        return False

    shutil.copy2(backup_path, settings_path)
    log.info(f"  settings.py 已从备份恢复: {backup_path}")
    return True


def create_settings_sqlite_fallback(settings_path):
    """
    创建一个临时 SQLite 配置文件用于数据导出
    返回临时配置文件路径
    """
    import tempfile
    import textwrap

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(settings_path)))
    tmp_settings = os.path.join(base_dir, 'ops_platform', 'settings_sqlite_temp.py')

    content = textwrap.dedent(f"""
        # Auto-generated SQLite fallback for migration data export
        from .settings import *

        DATABASES = {{
            'default': {{
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': r'{base_dir}\\db.sqlite3',
            }}
        }}
    """)

    with open(tmp_settings, 'w', encoding='utf-8') as f:
        f.write(content)

    return tmp_settings


def verify_pg_connection_from_settings(settings_path):
    """验证修改后的 settings.py 能否连接 PostgreSQL"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(settings_path)))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')

    try:
        import django
        django.setup()
        from django.db import connection
        cur = connection.cursor()
        cur.execute("SELECT version();")
        ver = cur.fetchone()[0]
        cur.close()
        log.info(f"  PostgreSQL 连接验证成功: {ver[:50]}...")
        return True
    except Exception as e:
        log.error(f"  PostgreSQL 连接失败: {e}")
        return False
