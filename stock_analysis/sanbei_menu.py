#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三倍量B点策略 — 菜单启动器
抖音 @开心 教学策略
"""
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path("D:/1989n/stock_analysis")
SIGNAL_DIR = Path("D:/1989n/stock_data/signals")
SCRIPT = BASE_DIR / "3倍量B点.py"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def show_menu():
    clear()
    print("=" * 55)
    print("  三倍量B点 策略扫描仪")
    print("  抖音 @开心 教学策略")
    print("=" * 55)
    print()
    print("策略三步:")
    print("  (1) 每天收盘后找 3倍量 股票加自选")
    print("  (2) 等缩量回踩 20日均线")
    print("  (3) 缩量止跌 + 小实体K线 = B点买入")
    print()
    print("-" * 55)
    print("  [1] 扫描持仓(7只)")
    print("  [2] 全市场扫描(排除科创板/ST)")
    print("  [3] 扫描单只股票")
    print("  [4] 查看上次信号报告")
    print("  [5] 退出")
    print("-" * 55)


def run_scan(code=""):
    clear()
    print("正在扫描，请稍候...\n")
    cmd = [sys.executable, str(SCRIPT)]
    if code and code != "--full":
        cmd.append(code)
    elif code == "--full":
        pass  # 默认就是全市场, 不加参数
    else:
        cmd.append("--watch")
    try:
        subprocess.run(cmd, cwd=str(BASE_DIR), check=True)
    except subprocess.CalledProcessError:
        print(f"\n扫描出错")
    input("\n按回车返回菜单")


def show_report():
    clear()
    files = sorted(SIGNAL_DIR.glob("3倍量B点_*.json"), reverse=True)
    if not files:
        print("暂无信号文件")
        input("\n按回车返回")
        return

    latest = files[0]
    print(f"最近信号: {latest.name}")
    print(f"修改时间: {os.path.getmtime(latest)}\n")

    try:
        import json
        data = json.loads(latest.read_text(encoding="utf-8"))
        print(f"  B点信号: {data.get('total_signals', 0)} 只")
        print(f"  持仓信号: {data.get('watchlist_signals', 0)} 只")
        print(f"  接近信号: {len(data.get('near_misses', []))} 只")
    except Exception as e:
        print(f"无法读取: {e}")

    print(f"\n路径: {latest}")
    if input("打开文件夹? (y/n): ").lower() == "y":
        os.startfile(str(SIGNAL_DIR))
    input("\n按回车返回")


def main():
    while True:
        show_menu()
        choice = input("请选择 (1-5): ").strip()
        if choice == "1":
            run_scan()
        elif choice == "2":
            run_scan("--full")
        elif choice == "3":
            code = input("输入股票代码: ").strip()
            if code:
                run_scan(code)
        elif choice == "4":
            show_report()
        elif choice == "5":
            print("bye")
            break
        else:
            input("无效选择，按回车重试")


if __name__ == "__main__":
    main()
