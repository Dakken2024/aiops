#!/usr/bin/env python3
"""
为现有 AgentToken 生成 hmac_secret 的辅助脚本。
用法:
    python scripts/generate_agent_hmac.py
"""
import os
import sys
import secrets

# 将项目根目录加入路径，以便导入 Django 设置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')

import django
django.setup()

from monitoring.models import AgentToken


def main():
    tokens = AgentToken.objects.filter(hmac_secret='')
    total = tokens.count()
    if total == 0:
        print("没有需要更新的 AgentToken（所有记录都已配置 hmac_secret）。")
        return

    updated = 0
    for token_obj in tokens:
        token_obj.hmac_secret = secrets.token_hex(32)
        token_obj.save(update_fields=['hmac_secret'])
        updated += 1
        print(f"Updated: {token_obj.name} -> {token_obj.hmac_secret[:8]}...")

    print(f"\n完成：共更新 {updated} 条 AgentToken 记录。")


if __name__ == '__main__':
    main()
