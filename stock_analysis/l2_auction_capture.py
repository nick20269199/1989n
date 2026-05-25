"""
l2_auction_capture.py — 东方财富 L2 竞价数据自动采集
====================================================
在 9:25 竞价窗口自动循环切换 5 只持仓股票，确保每只股票的
逐笔成交 .dat 文件都能捕获到竞价期间的 L2 数据。

原理:
  东方财富 PC 客户端只在用户"正在查看"某只股票时，才会将
  该股票的 L2 逐笔成交数据写入 DealL2File 目录下的 .dat 文件。
  手动切 5 只股票需要 ~60s，竞价窗口只有 ~25s。
  本脚本用 Win32 API 模拟键盘输入，在 20s 内自动完成 5 只
  股票的循环切换。

用法:
  # 手动运行（测试）
  python l2_auction_capture.py

  # 定时任务 (Windows Task Scheduler, 9:24:55 触发)
  run_l2_capture.bat

前置条件:
  - 东方财富 PC 客户端已启动，且当前在"逐笔成交"页面
  - Python 3.x + pyautogui (可选，用于备用方案)
"""

import ctypes
import time
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── 配置 ──

PORTFOLIO_PATH = Path("D:/1989n/stock_analysis/data/portfolio.json")
STOCK_DATA = Path("D:/1989n/stock_data")
LOG_PATH = STOCK_DATA / "l2_capture_log.json"

# 每只股票的查看时长（秒）
VIEW_SECONDS_PER_STOCK = 4

# 东方财富窗口标题关键词
EAST_MONEY_TITLES = ["东方财富终端"]  # 主窗口，优先匹配

# ── Win32 API ──

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_RETURN = 0x0D
VK_BACK = 0x08
VK_0 = 0x30
VK_1 = 0x31

KEYEVENTF_KEYUP = 0x0002

# 数字键虚拟码映射
_DIGIT_VK = {str(i): VK_0 + i for i in range(10)}


def _key_down(vk: int):
    user32.keybd_event(vk, 0, 0, 0)


def _key_up(vk: int):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _press_key(vk: int):
    _key_down(vk)
    time.sleep(0.03)
    _key_up(vk)
    time.sleep(0.03)


def type_stock_code(code: str):
    """键入股票代码 + 回车，切换东方财富当前查看的股票。"""
    # 先清空当前输入（连续按 Backspace）
    for _ in range(10):
        _press_key(VK_BACK)
    time.sleep(0.05)

    # 逐位输入代码
    for ch in code:
        vk = _DIGIT_VK.get(ch)
        if vk is not None:
            _press_key(vk)
            time.sleep(0.02)

    time.sleep(0.08)
    # 回车确认
    _press_key(VK_RETURN)


def find_eastmoney_window() -> Optional[int]:
    """查找东方财富主窗口句柄。"""
    FALLBACK_TITLES = ["东方财富证券", "东方财富"]

    def _lookup(keywords):
        results = []
        def enum_callback(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    for kw in keywords:
                        if kw in buf.value:
                            results.append(hwnd)
                            break
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        return results

    titles = _lookup(EAST_MONEY_TITLES)
    if titles:
        return titles[0]
    # 主窗口未找到时尝试其他包含"东方财富"的窗口
    return _lookup(FALLBACK_TITLES)[0] if _lookup(FALLBACK_TITLES) else None


def focus_window(hwnd: int) -> bool:
    """将窗口带到前台。"""
    # 如果窗口最小化了，先恢复
    SW_RESTORE = 9
    SW_SHOW = 5
    user32.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(0.1)
    # 设为前台窗口
    result = user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return result != 0


def focus_window_force(hwnd: int) -> bool:
    """强制将窗口带到前台（处理前台锁定的回退方案）。"""
    # 方法 1: 直接尝试
    if focus_window(hwnd):
        return True

    # 方法 2: 用 Alt 键技巧绕过前台锁定限制
    # 模拟按下 Alt 键（这会允许 SetForegroundWindow 在当前进程工作）
    user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU = Alt
    time.sleep(0.03)
    user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    return focus_window(hwnd)


def load_portfolio_codes() -> list[str]:
    """从 portfolio.json 加载持仓股票代码列表。"""
    if not PORTFOLIO_PATH.exists():
        print("[ERROR] portfolio.json not found, using fallback codes")
        return ["002156", "300136", "600498", "002077", "300058"]

    pf = json.loads(PORTFOLIO_PATH.read_text("utf-8"))
    if isinstance(pf, dict):
        holdings = pf.get("holdings", pf.get("data", []))
    else:
        holdings = pf if isinstance(pf, list) else []

    codes = []
    for h in holdings:
        code = h.get("code", h.get("stock_code", ""))
        if code:
            codes.append(code)
    return codes if codes else ["002156", "300136", "600498", "002077", "300058"]


def save_log(codes: list[str], results: list[dict]):
    """保存采集日志。"""
    log = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "codes_attempted": codes,
        "results": results,
    }
    LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), "utf-8")


# ═══════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════

def run_capture(dry_run: bool = False) -> bool:
    """
    执行 L2 竞价数据自动采集。

    1. 查找东方财富窗口
    2. 激活窗口
    3. 循环切换持仓股票，每只停留 VIEW_SECONDS_PER_STOCK 秒
    4. 记录采集日志

    Args:
        dry_run: True 时不操作窗口，只打印计划

    Returns:
        是否成功完成全部切换
    """
    codes = load_portfolio_codes()
    print(f"[{datetime.now():%H:%M:%S}] L2 竞价采集启动，共 {len(codes)} 只票: {codes}")

    if dry_run:
        print("  [DRY RUN] 不实际操作窗口")
        for i, code in enumerate(codes):
            print(f"  [{i+1}/{len(codes)}] {code} — 模拟切换，停留 {VIEW_SECONDS_PER_STOCK}s")
            print(f"  [DRY RUN] 总耗时: {len(codes) * VIEW_SECONDS_PER_STOCK}s")
        return True

    # 查找窗口
    hwnd = find_eastmoney_window()
    if not hwnd:
        print("[FAIL] 未找到东方财富窗口，请确认客户端已启动")
        return False

    print(f"  窗口句柄: {hwnd}")

    # 激活窗口
    if not focus_window_force(hwnd):
        print("[FAIL] 无法激活东方财富窗口")
        return False

    print(f"  窗口已激活，开始循环切换...")

    results = []
    for i, code in enumerate(codes):
        tick = datetime.now()
        print(f"  [{i+1}/{len(codes)}] {code} @ {tick:%H:%M:%S}")

        try:
            type_stock_code(code)
            results.append({"code": code, "time": tick.strftime("%H:%M:%S"),
                            "status": "switched"})
        except Exception as e:
            results.append({"code": code, "time": tick.strftime("%H:%M:%S"),
                            "status": "error", "error": str(e)})
            print(f"    [ERROR] {e}")

        # 在最后一只股票不需要额外等待
        if i < len(codes) - 1:
            time.sleep(VIEW_SECONDS_PER_STOCK)

    elapsed = (datetime.now() - tick).total_seconds() + (len(codes) - 1) * VIEW_SECONDS_PER_STOCK
    print(f"[{datetime.now():%H:%M:%S}] 采集完成，总耗时 ~{elapsed:.0f}s")
    save_log(codes, results)
    return all(r["status"] == "switched" for r in results)


# ═══════════════════════════════════════════════════
# 备用方案: pyautogui 实现
# ═══════════════════════════════════════════════════

def run_capture_pyautogui(codes: list[str] = None):
    """使用 pyautogui 的备用采集方案（需要 pip install pyautogui）。"""
    import pyautogui

    if codes is None:
        codes = load_portfolio_codes()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.03

    for i, code in enumerate(codes):
        print(f"  [{i+1}/{len(codes)}] {code}")
        pyautogui.press("backspace", presses=10, interval=0.01)
        pyautogui.write(code, interval=0.02)
        pyautogui.press("enter")
        if i < len(codes) - 1:
            time.sleep(VIEW_SECONDS_PER_STOCK)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "-n" in sys.argv
    use_pyautogui = "--pyautogui" in sys.argv

    if use_pyautogui:
        print("[INFO] 使用 pyautogui 备用方案")
        run_capture_pyautogui()
    else:
        success = run_capture(dry_run=dry)
        sys.exit(0 if success else 1)
