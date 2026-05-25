#!/usr/bin/env python3
"""
Fernet Key 生成脚本

用法:
    python scripts/generate_fernet_key.py

功能:
    1. 生成新的 Fernet Key
    2. 自动写入 .env 文件（如果存在）
    3. 提示重启服务
"""

import os
import sys
from pathlib import Path


def generate_fernet_key():
    """生成 Fernet Key"""
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        return key
    except ImportError:
        print("错误: 未安装 cryptography 库，请先运行: pip install cryptography")
        sys.exit(1)


def update_env_file(key: str):
    """更新 .env 文件"""
    env_path = Path(__file__).resolve().parent.parent / '.env'

    if not env_path.exists():
        print(f"警告: 未找到 .env 文件 ({env_path})")
        print("请手动将以下密钥添加到环境变量:")
        print(f"  APP_MASTER_KEY={key}")
        return False

    content = env_path.read_text(encoding='utf-8')

    # 检查是否已存在 APP_MASTER_KEY
    if 'APP_MASTER_KEY=' in content:
        # 替换现有密钥
        import re
        content = re.sub(
            r'APP_MASTER_KEY=.*',
            f'APP_MASTER_KEY={key}',
            content
        )
        print("已更新 .env 文件中的 APP_MASTER_KEY")
    else:
        # 在文件末尾添加
        content += f"\n# Fernet 加密密钥 (自动生成)\nAPP_MASTER_KEY={key}\n"
        print("已在 .env 文件中添加 APP_MASTER_KEY")

    env_path.write_text(content, encoding='utf-8')
    return True


def main():
    print("=" * 60)
    print("AiOps Fernet Key 生成工具")
    print("=" * 60)

    # 生成密钥
    key = generate_fernet_key()
    print(f"\n生成的密钥: {key}")

    # 更新 .env 文件
    updated = update_env_file(key)

    print("\n" + "=" * 60)
    print("重要提示:")
    print("=" * 60)
    print("1. 请妥善保管此密钥，丢失后将无法解密已有数据")
    print("2. 修改密钥后，所有已加密的字段将无法解密")
    print("3. 请重启 Django 服务使新密钥生效:")
    print("   python manage.py runserver")
    print("=" * 60)

    if not updated:
        print("\n请手动设置环境变量:")
        print(f"  export APP_MASTER_KEY={key}")


if __name__ == '__main__':
    main()
