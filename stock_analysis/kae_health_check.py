"""
kae_health_check.py — KAE 组件健康巡检

检查项:
  1. gap_registry.json — 存在 + 有效 JSON + 可解析缺口
  2. prospector_log.json — 存在 + 有效 JSON
  3. incremental_state.json — 存在 + 有 last_run_at
  4. vv_radar.db — 存在 + 有转录数据
  5. knowledge/ 目录完整性 — 必要子目录存在
  6. 模块导入 — knowledge_prospector / knowledge_abu sorber 可导入
  7. TF-IDF 依赖 — sklearn 可导入

用法:
  python kae_health_check.py
  python kae_health_check.py --json    # JSON 格式输出
"""
import json
import sys
import sqlite3
import importlib
from pathlib import Path

STOCK_ANALYSIS = Path("D:/1989n/stock_analysis")
STOCK_DATA = Path("D:/1989n/stock_data")
KNOWLEDGE_DIR = STOCK_DATA / "knowledge"

# 检查定义: (名称, 严重度, 检查函数)
CHECKS = []


def check(name: str, severity: str):
    """注册检查项。"""
    def decorator(fn):
        CHECKS.append((name, severity, fn))
        return fn
    return decorator


def _result(pass_: bool, detail: str = "") -> dict:
    return {"pass": pass_, "detail": detail}


# ── 检查项 ──


@check("gap_registry.json", "critical")
def _check_gap_registry():
    fp = KNOWLEDGE_DIR / "gap_registry.json"
    if not fp.exists():
        return _result(False, f"文件不存在: {fp}")
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return _result(False, f"JSON解析失败: {e}")
    if not isinstance(data, list):
        return _result(False, f"格式错误: 应为列表, 得到 {type(data).__name__}")
    open_count = sum(1 for g in data if g.get("status") == "open")
    total = len(data)
    return _result(True, f"{total} 个缺口, {open_count} 个开放中")


@check("prospector_log.json", "critical")
def _check_prospector_log():
    fp = KNOWLEDGE_DIR / "prospector_log.json"
    if not fp.exists():
        return _result(False, f"文件不存在: {fp}")
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return _result(False, f"JSON解析失败: {e}")
    if not isinstance(data, list):
        return _result(False, f"格式错误")
    absorbed = sum(1 for f in data if f.get("absorbed"))
    return _result(True, f"{len(data)} 条发现, {absorbed} 条已吸收")


@check("incremental_state.json", "warning")
def _check_incremental():
    fp = KNOWLEDGE_DIR / "incremental_state.json"
    if not fp.exists():
        return _result(False, "增量状态文件不存在 (首次运行无需担心)")
    try:
        state = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return _result(False, f"JSON解析失败: {e}")
    last_run = state.get("last_run_at", "")
    mode = state.get("mode", "unknown")
    if not last_run:
        return _result(False, "缺少 last_run_at 字段")
    return _result(True, f"上次运行: {last_run[:19]}, 模式: {mode}")


@check("vv_radar.db", "warning")
def _check_vv_db():
    fp = STOCK_DATA / "vv_radar.db"
    if not fp.exists():
        return _result(False, f"数据库不存在: {fp}")
    try:
        conn = sqlite3.connect(str(fp))
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM vv_videos")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM vv_videos WHERE transcript_text IS NOT NULL AND transcript_text != ''")
        transcribed = c.fetchone()[0]
        conn.close()
        return _result(True, f"{total} 条视频, {transcribed} 条已转录")
    except Exception as e:
        return _result(False, f"数据库异常: {e}")


@check("knowledge/ 目录结构", "critical")
def _check_knowledge_dir():
    if not KNOWLEDGE_DIR.exists():
        return _result(False, f"目录不存在: {KNOWLEDGE_DIR}")
    required = ["findings", "proposals"]
    missing = [d for d in required if not (KNOWLEDGE_DIR / d).exists()]
    if missing:
        return _result(False, f"缺少子目录: {missing}")
    return _result(True, "目录结构完整")


@check("模块导入", "critical")
def _check_imports():
    import sys as _sys
    _sys.path.insert(0, str(STOCK_ANALYSIS))
    modules = ["knowledge_prospector", "knowledge_absorber",
               "knowledge_gap_registry", "knowledge_tracer"]
    failed = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            failed.append(f"{mod}: {e}")
    if failed:
        return _result(False, "; ".join(failed))
    return _result(True, f"{len(modules)}/{len(modules)} 模块导入成功")


@check("TF-IDF 依赖", "critical")
def _check_tfidf():
    try:
        import sklearn
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        version = sklearn.__version__
        return _result(True, f"scikit-learn {version} 可用")
    except ImportError as e:
        return _result(False, f"缺少依赖: {e}")


@check("提案目录", "info")
def _check_proposals():
    prop_dir = KNOWLEDGE_DIR / "proposals"
    if not prop_dir.exists():
        return _result(False, "目录不存在")
    props = list(prop_dir.glob("*.json"))
    if not props:
        return _result(False, "无提案文件")
    return _result(True, f"{len(props)} 个提案文件")


# ── 主入口 ──


def run_checks(output_json: bool = False) -> dict:
    """执行全部巡检，返回结果字典。"""
    results = {}
    all_pass = True
    for name, severity, fn in CHECKS:
        try:
            r = fn()
        except Exception as e:
            r = _result(False, f"检查异常: {e}")
        if not r["pass"]:
            all_pass = False
        results[name] = {**r, "severity": severity}

    summary = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "all_pass": all_pass,
        "total_checks": len(CHECKS),
        "passed": sum(1 for r in results.values() if r["pass"]),
        "failed": sum(1 for r in results.values() if not r["pass"]),
        "results": results,
    }

    if output_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("=" * 50)
        print("KAE 健康巡检")
        print(f"时间: {summary['timestamp'][:19]}")
        print("=" * 50)
        for name, r in results.items():
            icon = "PASS" if r["pass"] else "FAIL"
            sev = r.get("severity", "info")
            print(f"  [{icon}] [{sev}] {name}")
            print(f"         {r['detail']}")
        print("-" * 50)
        print(f"总计: {summary['passed']}/{summary['total_checks']} 通过, "
              f"{summary['failed']} 失败")
        print(f"整体: {'PASS' if all_pass else 'FAIL'}")

    return summary


if __name__ == "__main__":
    output_json = "--json" in sys.argv
    run_checks(output_json=output_json)
