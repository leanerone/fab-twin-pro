#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FabTwin v2.0 数据迁移脚本

功能：
1. 为 machine_model_configs 表添加新字段（animation_config_json, source_files_json）
2. 将 frontend/src/configs/machine-animations/*.json 内容写入 DB
3. 验证迁移结果

使用方式：
  python migrate_animation_config.py --dry-run    # 仅预览，不执行
  python migrate_animation_config.py              # 执行迁移
  python migrate_animation_config.py --verify     # 验证结果
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db, engine
from sqlalchemy import text
from models import MachineModelConfig


def get_animation_configs():
    """读取 frontend/src/configs/machine-animations/*.json 文件"""
    configs = {}
    config_dir = os.path.join(
        os.path.dirname(__file__),
        '..', 'frontend', 'src', 'configs', 'machine-animations'
    )

    if not os.path.exists(config_dir):
        print(f"[WARN] 配置目录不存在: {config_dir}")
        return configs

    for filename in os.listdir(config_dir):
        if filename.endswith('.json') and not filename.startswith('_'):
            filepath = os.path.join(config_dir, filename)
            config_name = filename[:-5]  # 去掉 .json
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    configs[config_name] = config_data
                    print(f"[INFO] 读取配置: {filename} ({len(json.dumps(config_data))} bytes)")
            except Exception as e:
                print(f"[ERROR] 读取失败: {filename}, {e}")

    return configs


def add_columns_sqlite():
    """SQLite: 添加新字段"""
    try:
        with engine.connect() as conn:
            # 检查字段是否已存在
            result = conn.execute(text("PRAGMA table_info(machine_model_configs)"))
            columns = [row[1] for row in result.fetchall()]

            if 'animation_config_json' not in columns:
                conn.execute(text(
                    "ALTER TABLE machine_model_configs ADD COLUMN animation_config_json TEXT DEFAULT '{}'"
                ))
                print("[OK] SQLite: 添加字段 animation_config_json")

            if 'source_files_json' not in columns:
                conn.execute(text(
                    "ALTER TABLE machine_model_configs ADD COLUMN source_files_json TEXT DEFAULT '{}'"
                ))
                print("[OK] SQLite: 添加字段 source_files_json")

            conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] SQLite 添加字段失败: {e}")
        return False


def add_columns_oracle():
    """Oracle: 添加新字段（使用动态 SQL 检查字段是否存在）"""
    try:
        with engine.connect() as conn:
            # 检查 animation_config_json 是否存在
            result = conn.execute(text("""
                SELECT COUNT(*) FROM user_tab_columns
                WHERE table_name = 'MACHINE_MODEL_CONFIGS'
                AND column_name = 'ANIMATION_CONFIG_JSON'
            """))
            if result.fetchone()[0] == 0:
                conn.execute(text("""
                    ALTER TABLE machine_model_configs ADD (
                        animation_config_json CLOB DEFAULT '{}'
                    )
                """))
                print("[OK] Oracle: 添加字段 animation_config_json")
            else:
                print("[INFO] Oracle: 字段 animation_config_json 已存在")

            # 检查 source_files_json 是否存在
            result = conn.execute(text("""
                SELECT COUNT(*) FROM user_tab_columns
                WHERE table_name = 'MACHINE_MODEL_CONFIGS'
                AND column_name = 'SOURCE_FILES_JSON'
            """))
            if result.fetchone()[0] == 0:
                conn.execute(text("""
                    ALTER TABLE machine_model_configs ADD (
                        source_files_json CLOB DEFAULT '{}'
                    )
                """))
                print("[OK] Oracle: 添加字段 source_files_json")
            else:
                print("[INFO] Oracle: 字段 source_files_json 已存在")

            conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Oracle 添加字段失败: {e}")
        return False


def add_columns():
    """根据数据库类型添加字段"""
    db_url = str(engine.url)
    if 'sqlite' in db_url.lower():
        return add_columns_sqlite()
    elif 'oracle' in db_url.lower():
        return add_columns_oracle()
    else:
        print(f"[WARN] 未知数据库类型: {db_url}")
        return False


def migrate_configs(dry_run=False):
    """迁移动画配置到数据库"""
    configs = get_animation_configs()
    if not configs:
        print("[WARN] 未找到任何配置文件")
        return

    # 配置文件名到 model_id 的映射
    config_to_model = {
        'podopener': 'PODOPENER-2200',
        # 未来可以添加更多映射
    }

    db = next(get_db())
    now = datetime.now(timezone.utc).isoformat()

    migrated_count = 0

    for config_name, config_data in configs.items():
        model_id = config_to_model.get(config_name)
        if not model_id:
            print(f"[WARN] 未找到配置 '{config_name}' 对应的 model_id，跳过")
            continue

        # 查找机型记录
        model = db.query(MachineModelConfig).filter(
            MachineModelConfig.model_id == model_id
        ).first()

        if not model:
            print(f"[WARN] 数据库中未找到机型: {model_id}，跳过")
            continue

        config_json = json.dumps(config_data, ensure_ascii=False)

        if dry_run:
            print(f"[DRY-RUN] 将更新 {model_id}:")
            print(f"  - animation_config_json: {len(config_json)} bytes")
            print(f"  - machine_type: {config_data.get('machine_type', 'N/A')}")
            print(f"  - flows: {list(config_data.get('flows', {}).keys())}")
        else:
            model.animation_config_json = config_json
            model.updated_at = now
            migrated_count += 1
            print(f"[OK] 更新 {model_id}: animation_config_json ({len(config_json)} bytes)")

    if not dry_run:
        db.commit()
        print(f"\n[SUCCESS] 迁移完成，共更新 {migrated_count} 条记录")
    else:
        print(f"\n[DRY-RUN] 预览完成，未执行实际更新")


def verify_migration():
    """验证迁移结果"""
    db = next(get_db())

    models = db.query(MachineModelConfig).all()
    print(f"\n验证结果（共 {len(models)} 个机型）:")
    print("-" * 80)

    for model in models:
        config = getattr(model, 'animation_config_json', None) or '{}'
        config_data = {}
        try:
            config_data = json.loads(config) if config else {}
        except:
            pass

        print(f"\n机型: {model.model_id}")
        print(f"  名称: {model.model_name}")
        print(f"  视图模式: {model.view_mode}")
        print(f"  动画配置大小: {len(config)} bytes")
        if config_data:
            print(f"  配置类型: {config_data.get('machine_type', 'N/A')}")
            print(f"  流程数: {len(config_data.get('flows', {}))}")
            print(f"  动画原语数: {len(config_data.get('animations', {}))}")
            print(f"  目标部件数: {len(config_data.get('targets', {}))}")


def main():
    parser = argparse.ArgumentParser(description='FabTwin v2.0 数据迁移脚本')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不执行')
    parser.add_argument('--verify', action='store_true', help='验证迁移结果')
    parser.add_argument('--columns-only', action='store_true', help='仅添加字段，不迁移数据')

    args = parser.parse_args()

    print("=" * 80)
    print("FabTwin v2.0 数据迁移脚本")
    print("=" * 80)

    if args.verify:
        verify_migration()
        return

    print("\n步骤 1: 添加数据库字段...")
    if not add_columns():
        print("[ERROR] 添加字段失败，终止迁移")
        return

    if args.columns_only:
        print("\n[INFO] 仅添加字段模式，跳过数据迁移")
        return

    print("\n步骤 2: 迁移动画配置到数据库...")
    migrate_configs(dry_run=args.dry_run)

    if not args.dry_run:
        print("\n步骤 3: 验证迁移结果...")
        verify_migration()

    print("\n" + "=" * 80)
    print("迁移完成!")
    print("=" * 80)


if __name__ == '__main__':
    main()