#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Полный скрипт для выполнения всех git операций
"""
import subprocess
import os
import shutil
from pathlib import Path

def run_git(cmd):
    """Выполняет git команду"""
    try:
        result = subprocess.run(
            ['git'] + cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            shell=False
        )
        if result.stdout:
            print(f"  {result.stdout.strip()}")
        if result.stderr and result.returncode != 0:
            print(f"  Ошибка: {result.stderr.strip()}")
        return result.returncode == 0
    except Exception as e:
        print(f"  Исключение: {e}")
        return False

def main():
    print("=" * 60)
    print("Выполнение операций с git")
    print("=" * 60)
    
    # 1. Проверяем текущую ветку
    print("\n1. Проверка текущей ветки...")
    result = subprocess.run(['git', 'branch', '--show-current'], 
                          capture_output=True, text=True, encoding='utf-8')
    current_branch = result.stdout.strip()
    print(f"   Текущая ветка: {current_branch}")
    
    # 2. Создаём/переключаемся на development
    print("\n2. Работа с веткой development...")
    if current_branch != 'development':
        print("   Создание ветки development...")
        if not run_git(['checkout', '-b', 'development']):
            print("   Переключение на существующую ветку development...")
            run_git(['checkout', 'development'])
    else:
        print("   Уже на ветке development")
    
    # 3. Коммитим все файлы в development
    print("\n3. Сохранение всех файлов в development...")
    run_git(['add', '-A'])
    if run_git(['commit', '-m', 'chore: сохранение текущего прогресса в ветку development']):
        print("   ✓ Файлы сохранены в development")
    else:
        print("   ⚠️  Возможно, нет изменений для коммита")
    
    # 4. Переключаемся на main
    print("\n4. Переключение на main...")
    run_git(['checkout', 'main'])
    print("   ✓ Переключились на main")
    
    # 5. Удаляем ненужные файлы
    print("\n5. Удаление ненужных файлов...")
    keep_items = {'.git', '.gitignore', 'context_project', 'Articles.xlsx', 
                  '.env', '.env_sample', '.cursor'}
    
    # Удаляем папку src
    src_path = Path('src')
    if src_path.exists():
        try:
            shutil.rmtree(src_path)
            print("   ✓ Удалена папка src")
        except Exception as e:
            print(f"   ⚠️  Ошибка при удалении src: {e}")
    
    # Удаляем другие файлы
    files_to_delete = []
    for item in os.listdir('.'):
        if item not in keep_items and not item.startswith('.'):
            item_path = Path(item)
            if item_path.exists():
                files_to_delete.append(item)
    
    for item in files_to_delete:
        try:
            item_path = Path(item)
            if item_path.is_file():
                item_path.unlink()
                print(f"   ✓ Удалён файл: {item}")
            elif item_path.is_dir():
                shutil.rmtree(item_path)
                print(f"   ✓ Удалена папка: {item}")
        except Exception as e:
            print(f"   ⚠️  Ошибка при удалении {item}: {e}")
    
    # 6. Коммитим изменения в main
    print("\n6. Коммит изменений в main...")
    run_git(['add', '-A'])
    if run_git(['commit', '-m', 'chore: очистка main ветки, оставлены только необходимые файлы']):
        print("   ✓ Изменения закоммичены в main")
    else:
        print("   ⚠️  Возможно, нет изменений для коммита")
    
    # 7. Показываем финальный статус
    print("\n7. Финальный статус...")
    result = subprocess.run(['git', 'branch', '--show-current'], 
                          capture_output=True, text=True, encoding='utf-8')
    current_branch = result.stdout.strip()
    print(f"   Текущая ветка: {current_branch}")
    
    print("\n" + "=" * 60)
    print("Операции завершены!")
    print("=" * 60)
    print("\nДля отправки в GitHub выполните:")
    print("  git checkout development")
    print("  git push -u origin development")
    print("  git checkout main")
    print("  git push origin main")

if __name__ == "__main__":
    main()

