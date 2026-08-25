"""
一键清理脚本 - 支持全部清理或按日期范围清理
用法: python clean_all.py
"""

import os
import shutil
import sys
import fnmatch
from pathlib import Path
from datetime import datetime, timedelta
import time

# ==================== 配置 ====================
# 保留的目录（不扫描）
KEEP_DIRS = {
    'core',
    'config',
    'pybao',
    'data',
    'outputs',
    '.git',
}

# 根目录保留的文件
ROOT_KEEP_FILES = {
    'app.py',
    'main.py',
    'config.py',
    'requirements.txt',
    'README.md',
    'README_project.md',
    'stock_list.csv',
    'myStock.csv',
    '.gitignore',
    'clean_all.py',
}

# 要删除的文件模式（递归）
DELETE_PATTERNS = [
    '*.bak',
    '*.bak_*',
    '*.tmp',
    '*.log',
    '*.pkl',
    '*.pkl.bak',
    '*.pyc',
    '*.pyo',
    '*.fig',
    '*.png',
    '*.jpg',
    '*.jpeg',
    '*.gif',
    '*.svg',
    '*.bmp',
    '*.tiff',
    '*.xlsx',
    '*.xls',
    '__pycache__',
    '.DS_Store',
    'Thumbs.db',
    '*.swp',
    '*.swo',
]

# 根目录删除的文件模式（不递归）
ROOT_DELETE_PATTERNS = [
    'apply_*.py',
    'fix_*.py',
    'patch*.py',
    'diagnose*.py',
    'debug*.py',
    'test_*.py',
    'clean*.py',
    'deep_clean.py',
    'reorganize_project.py',
    'rebuild_*.py',
    'create_*.py',
    'cleanup*.py',
    '111',
    '*.html',
]

# 根目录删除的目录
ROOT_DELETE_DIRS = [
    '.streamlit',
    '.pytest_cache',
    '.mypy_cache',
    'trash_*',
]

# ==================== 辅助函数 ====================
def get_file_time(filepath):
    try:
        return datetime.fromtimestamp(os.path.getmtime(filepath))
    except:
        return None

def should_delete_root(filename):
    if filename in ROOT_KEEP_FILES:
        return False
    for pattern in ROOT_DELETE_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False

def should_delete_recursive(filepath, root_path):
    rel_path = os.path.relpath(filepath, root_path)
    parts = Path(rel_path).parts
    if parts and parts[0] in KEEP_DIRS:
        return False
    basename = os.path.basename(filepath)
    for pattern in DELETE_PATTERNS:
        if fnmatch.fnmatch(basename, pattern):
            return True
    if os.path.isdir(filepath) and basename in ['__pycache__', '.pytest_cache', '.mypy_cache']:
        return True
    if os.path.isdir(filepath) and basename.startswith('trash_'):
        return True
    return False

def parse_date_input(date_str):
    date_str = date_str.strip()
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except:
        pass
    try:
        return datetime.strptime(date_str, '%Y%m%d')
    except:
        pass
    if date_str.startswith('-') and date_str.endswith('d'):
        days = int(date_str[1:-1])
        return datetime.now() - timedelta(days=days)
    if date_str.startswith('-') and date_str.endswith('天'):
        days = int(date_str[1:-1])
        return datetime.now() - timedelta(days=days)
    return None

def is_in_date_range(filepath, start_date, end_date):
    file_time = get_file_time(filepath)
    if file_time is None:
        return False
    if start_date and file_time < start_date:
        return False
    if end_date and file_time > end_date:
        return False
    return True

def create_backup_dir():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"trash_{timestamp}"
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir

def collect_files_to_delete(root_path, start_date=None, end_date=None):
    to_delete = []
    
    for item in os.listdir('.'):
        if item in ROOT_KEEP_FILES:
            continue
        full_path = os.path.join('.', item)
        if os.path.isfile(full_path) and should_delete_root(item):
            if is_in_date_range(full_path, start_date, end_date):
                to_delete.append(('file', full_path, item))

    for item in os.listdir('.'):
        full_path = os.path.join('.', item)
        if os.path.isdir(full_path):
            for pattern in ROOT_DELETE_DIRS:
                if fnmatch.fnmatch(item, pattern):
                    if is_in_date_range(full_path, start_date, end_date):
                        to_delete.append(('dir', full_path, item))
                    break

    for dirpath, dirnames, filenames in os.walk('.'):
        rel_dir = os.path.relpath(dirpath, '.')
        if rel_dir == '.':
            continue
        parts = Path(rel_dir).parts
        if parts and parts[0] in KEEP_DIRS:
            continue
        dirname = os.path.basename(dirpath)
        if dirname in ['__pycache__', '.pytest_cache', '.mypy_cache']:
            if is_in_date_range(dirpath, start_date, end_date):
                to_delete.append(('dir', dirpath, dirname))
            continue
        if dirname.startswith('trash_'):
            if is_in_date_range(dirpath, start_date, end_date):
                to_delete.append(('dir', dirpath, dirname))
            continue
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            if should_delete_recursive(full_path, root_path):
                if is_in_date_range(full_path, start_date, end_date):
                    to_delete.append(('file', full_path, filename))
    
    return to_delete

# ==================== 主界面 ====================
def show_menu():
    print("=" * 70)
    print("🧹 一键清理 - 从零开始")
    print("=" * 70)
    print()
    print("请选择清理模式：")
    print("  1. 全部清理（删除所有杂项文件）")
    print("  2. 按日期范围清理（只删除指定日期范围内的文件）")
    print("  3. 查看项目文件结构")
    print("  0. 退出")
    print()

def show_file_structure():
    print("\n📂 项目目录结构：")
    print("=" * 60)
    print("📁 E:\\stockgate\\Quant_Alpha_System\\")
    print("│")
    print("├── 📄 app.py          ✅ 核心-前端入口")
    print("├── 📄 main.py         ✅ 核心-命令行入口")
    print("├── 📄 config.py       ✅ 核心-配置")
    print("├── 📄 requirements.txt ✅ 依赖清单")
    print("├── 📄 *.csv           ✅ 用户数据")
    print("│")
    print("├── 📂 core/           ✅ 核心代码（全部保留）")
    print("├── 📂 config/         ✅ 配置文件（全部保留）")
    print("├── 📂 pybao/          ✅ SDK（全部保留）")
    print("├── 📂 data/           ✅ 用户数据（保留）")
    print("├── 📂 outputs/        ✅ 输出结果（保留）")
    print("│")
    print("├── 📄 *.bak           ❌ 备份文件")
    print("├── 📄 apply_*.py      ❌ 补丁脚本")
    print("├── 📄 fix_*.py        ❌ 修复脚本")
    print("├── 📄 patch*.py       ❌ 补丁脚本")
    print("├── 📄 diagnose*.py    ❌ 诊断脚本")
    print("├── 📄 test_*.py       ❌ 测试脚本")
    print("├── 📄 *.tmp/*.log     ❌ 临时文件")
    print("├── 📂 __pycache__/    ❌ Python缓存")
    print("├── 📂 .streamlit/     ❌ Streamlit缓存")
    print("├── 📂 trash_*/        ❌ 旧备份目录")
    print("=" * 60)
    print("💡 提示：运行此脚本可清理上述 ❌ 标记的文件\n")

def get_date_range():
    print("\n📅 按日期范围清理")
    print("支持格式:")
    print("  - YYYY-MM-DD  (如 2026-01-01)")
    print("  - YYYYMMDD    (如 20260101)")
    print("  - 相对日期    (如 -7d 表示7天前, -30d 表示30天前)")
    print("  - 直接回车    (不限制)")
    print()
    
    start_input = input("开始日期 (早于此日期的文件不删除，直接回车跳过): ").strip()
    end_input = input("结束日期 (晚于此日期的文件不删除，直接回车跳过): ").strip()
    
    start_date = parse_date_input(start_input) if start_input else None
    end_date = parse_date_input(end_input) if end_input else None
    
    if start_input and start_date is None:
        print(f"⚠️ 无法解析开始日期: {start_input}，将跳过此限制")
        start_date = None
    if end_input and end_date is None:
        print(f"⚠️ 无法解析结束日期: {end_input}，将跳过此限制")
        end_date = None
    
    if start_date and end_date and start_date > end_date:
        print("⚠️ 开始日期晚于结束日期，已自动交换")
        start_date, end_date = end_date, start_date
    
    return start_date, end_date

def main():
    if not os.path.exists("app.py"):
        print("❌ 请在项目根目录（包含 app.py 的目录）运行此脚本。")
        sys.exit(1)

    root_path = os.getcwd()

    while True:
        show_menu()
        choice = input("请输入选项: ").strip()

        if choice == '0':
            print("👋 退出。")
            break

        if choice == '3':
            show_file_structure()
            continue

        if choice not in ['1', '2']:
            print("❌ 无效选项，请重新选择。")
            continue

        start_date = None
        end_date = None
        if choice == '2':
            start_date, end_date = get_date_range()
            if not start_date and not end_date:
                print("⚠️ 未设置任何日期限制，将清理所有文件。")
                confirm = input("确认清理所有文件？输入 'yes' 继续: ")
                if confirm.lower() != 'yes':
                    print("❌ 操作已取消。")
                    continue
            else:
                date_info = []
                if start_date:
                    date_info.append(f"从 {start_date.strftime('%Y-%m-%d')} 起")
                if end_date:
                    date_info.append(f"到 {end_date.strftime('%Y-%m-%d')} 止")
                print(f"\n📅 将删除 {''.join(date_info)} 修改的文件。")
                confirm = input("确认继续？输入 'yes' 继续: ")
                if confirm.lower() != 'yes':
                    print("❌ 操作已取消。")
                    continue
        else:
            print("\n⚠️ 将删除所有杂项文件（不包括核心代码和用户数据）")
            confirm = input("确认继续？输入 'yes' 继续: ")
            if confirm.lower() != 'yes':
                print("❌ 操作已取消。")
                continue

        print("\n🔍 扫描文件...")
        to_delete = collect_files_to_delete(root_path, start_date, end_date)

        if not to_delete:
            print("✅ 没有发现需要删除的文件。")
            continue

        print(f"\n📋 共发现 {len(to_delete)} 个文件/目录需要删除：")
        for idx, (typ, path, name) in enumerate(to_delete[:30]):
            typ_label = "📁" if typ == 'dir' else "📄"
            if typ == 'file' and os.path.exists(path):
                mtime = get_file_time(path)
                time_str = mtime.strftime('%Y-%m-%d %H:%M') if mtime else '未知'
                print(f"  {idx+1}. {typ_label} {name} ({time_str})")
            else:
                print(f"  {idx+1}. {typ_label} {name}")
        if len(to_delete) > 30:
            print(f"  ... 还有 {len(to_delete)-30} 个文件")

        confirm2 = input(f"\n确认删除以上 {len(to_delete)} 个文件？输入 'yes' 确认: ")
        if confirm2.lower() != 'yes':
            print("❌ 操作已取消。")
            continue

        backup_dir = create_backup_dir()
        print(f"\n📁 备份目录: {backup_dir}")
        deleted_count = 0

        for typ, path, name in to_delete:
            try:
                if typ == 'dir':
                    dest = os.path.join(backup_dir, name)
                    if os.path.exists(dest):
                        dest = os.path.join(backup_dir, f"{name}_{deleted_count}")
                    shutil.move(path, dest)
                    print(f"  ✅ 移动目录: {name} -> {backup_dir}/")
                else:
                    rel_path = os.path.relpath(path, '.')
                    dest = os.path.join(backup_dir, rel_path)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if os.path.exists(dest):
                        base, ext = os.path.splitext(dest)
                        dest = f"{base}_{deleted_count}{ext}"
                    shutil.move(path, dest)
                    print(f"  ✅ 移动: {rel_path} -> {backup_dir}/")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ 移动失败: {name} - {e}")

        print("\n" + "=" * 70)
        print(f"🎉 清理完成！共移动 {deleted_count} 个文件/目录到备份。")
        print(f"备份目录: {backup_dir}")
        print("确认无误后可手动删除该备份目录。")
        print("=" * 70)

        break

if __name__ == "__main__":
    main()