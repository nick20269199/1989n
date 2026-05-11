"""
预测追踪闭环 v1 — 深度研究产出预测 → 自动验证 → 认知修正。

深度研究要求"1-3个可在未来N天验证的具体预测"，但这个反馈环
至今未闭合。本模块补齐 PDCA 的 C(检查) 阶段。

功能:
  1. 从深度研究输出中自动提取可验证预测
  2. 到达验证日期时自动检查预测是否应验
  3. 追踪预测准确率，用于修正研究者的置信度
  4. 发现预测持续失效时触发认知修正信号

用法:
    python forecast_closer.py                       # 检查所有到期预测
    python forecast_closer.py --extract 20260509    # 从指定日期的研究中提取预测
    python forecast_closer.py --report             # 输出预测准确率报告
    python forecast_closer.py --verify-all          # 验证所有未验证预测（手动确认）
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daily_compress import (
    load_json, save_json,
    LEARNING_DIR,
)

MODELS_DIR = LEARNING_DIR / "models"
FORECAST_FILE = LEARNING_DIR / "forecast_tracker.json"


def extract_predictions_from_text(text: str) -> list:
    """从研究文本中提取「可验证预测」部分。

    匹配模式:
    - ### 可验证预测
    - 1. [具体预测 + 验证时间]
    - 2. ...
    """
    predictions = []

    # 找到"可验证预测"章节
    patterns = [
        r'###\s*可验证预测\s*\n(.*?)(?=\n###|\n##|\Z)',
        r'可验证预测[：:]\s*\n(.*?)(?=\n#|\Z)',
    ]

    section = ""
    for pat in patterns:
        match = re.search(pat, text, re.DOTALL)
        if match:
            section = match.group(1)
            break

    if not section:
        return []

    # 提取编号条目
    items = re.findall(r'\d+\.\s*(.+?)(?=\n\d+\.|\n\n|\Z)', section, re.DOTALL)

    for item in items:
        item = item.strip()
        if not item:
            continue

        # 尝试提取验证时间
        # 模式: "验证时间: N天后" / "验证: N天后" / "N天内" / "N天后"
        days_match = re.search(r'(\d+)\s*天[后内]', item)
        verify_days = int(days_match.group(1)) if days_match else 7  # 默认7天

        prediction = {
            "text": item[:200],
            "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "verify_in_days": verify_days,
        }
        predictions.append(prediction)

    return predictions


def extract_from_research(date_str: str = "") -> list:
    """从指定日期（或最新）的深度研究产出中提取预测。"""
    if date_str:
        files = sorted(MODELS_DIR.glob(f"{date_str}_*.md"), reverse=True)
    else:
        files = sorted(MODELS_DIR.glob("*.md"), reverse=True)
        # 取今天的
        today = datetime.now().strftime("%Y%m%d")
        files = [f for f in files if f.name.startswith(today)] or files[:1]

    if not files:
        print("无深度研究产出文件。")
        return []

    all_predictions = []
    for fpath in files[:5]:  # 最多处理5个文件
        try:
            text = fpath.read_text(encoding="utf-8")
            predictions = extract_predictions_from_text(text)
            for p in predictions:
                p["source_file"] = fpath.name
                p["source_date"] = fpath.name[:8]
            all_predictions.extend(predictions)
            if predictions:
                print(f"  {fpath.name}: 提取 {len(predictions)} 条预测")
        except Exception as e:
            print(f"  {fpath.name}: 读取失败 ({e})")

    return all_predictions


def commit_predictions(predictions: list) -> list:
    """将提取的预测写入追踪文件。"""
    data = load_json(FORECAST_FILE)
    forecasts = data.get("forecasts", [])

    committed = []
    for p in predictions:
        source_date = p.get("source_date", datetime.now().strftime("%Y%m%d"))
        verify_date = (datetime.strptime(source_date, "%Y%m%d") +
                      timedelta(days=p.get("verify_in_days", 7))).strftime("%Y-%m-%d")

        fid = f"F{source_date}_{len(forecasts)+1:03d}"
        forecast = {
            "id": fid,
            "prediction": p["text"],
            "made_date": source_date,
            "verify_date": verify_date,
            "data_source": p.get("source_file", ""),
            "status": "pending",
            "result": "",
            "verified_at": "",
        }
        forecasts.append(forecast)
        committed.append(forecast)

    data["forecasts"] = forecasts
    data["stats"] = compute_stats(forecasts)
    save_json(FORECAST_FILE, data)

    return committed


def compute_stats(forecasts: list) -> dict:
    verified = [f for f in forecasts if f.get("status") in ("correct", "wrong")]
    return {
        "total": len(forecasts),
        "pending": len([f for f in forecasts if f.get("status") == "pending"]),
        "verified": len(verified),
        "correct": len([f for f in verified if f.get("status") == "correct"]),
        "wrong": len([f for f in verified if f.get("status") == "wrong"]),
        "accuracy": round(
            len([f for f in verified if f.get("status") == "correct"]) / max(len(verified), 1), 3
        ),
    }


def check_due_predictions(date_str: str = "") -> list:
    """检查所有到期但未验证的预测。"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    data = load_json(FORECAST_FILE)
    forecasts = data.get("forecasts", [])

    due = []
    for f in forecasts:
        if f.get("status") == "pending" and f.get("verify_date", "") <= date_str:
            due.append(f)

    return due


def verify_prediction(forecast_id: str, correct: bool, note: str = ""):
    """手动验证单条预测。"""
    data = load_json(FORECAST_FILE)
    forecasts = data.get("forecasts", [])

    for f in forecasts:
        if f.get("id") == forecast_id:
            f["status"] = "correct" if correct else "wrong"
            f["result"] = note
            f["verified_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            break

    data["stats"] = compute_stats(forecasts)
    save_json(FORECAST_FILE, data)


def generate_report() -> str:
    """生成预测追踪报告。"""
    data = load_json(FORECAST_FILE)
    forecasts = data.get("forecasts", [])
    stats = data.get("stats", {})

    report = f"""# 预测追踪报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**总预测数**: {stats.get('total', 0)}
**已验证**: {stats.get('verified', 0)} (正确: {stats.get('correct', 0)}, 错误: {stats.get('wrong', 0)})
**准确率**: {stats.get('accuracy', 0):.0%}
**待验证**: {stats.get('pending', 0)}

## 待验证预测

| ID | 预测 | 制定日期 | 验证日期 | 状态 |
|----|------|---------|---------|------|
"""
    pending = [f for f in forecasts if f.get("status") == "pending"]
    for f in pending[:10]:
        report += f"| {f['id']} | {f['prediction'][:60]} | {f['made_date']} | {f['verify_date']} | {f['status']} |\n"

    verified = [f for f in forecasts if f.get("status") in ("correct", "wrong")]
    if verified:
        report += "\n## 已验证预测\n\n| ID | 预测 | 结果 | 备注 |\n|----|------|------|------|\n"
        for f in verified[-10:]:
            emoji = "O" if f.get("status") == "correct" else "X"
            report += f"| {f['id']} | {f['prediction'][:50]} | {emoji} | {f.get('result','')[:30]} |\n"

    # 认知修正信号
    accuracy = stats.get("accuracy", 0)
    if stats.get("verified", 0) >= 5 and accuracy < 0.4:
        report += "\n## 认知修正信号\n\n**警告**: 预测准确率持续低于40%，建议:\n"
        report += "- 检查研究框架是否存在系统性偏差\n"
        report += "- 回顾失败预测的共同特征\n"
        report += "- 考虑增加不确定性标注的粒度\n"

    return report


def main():
    if "--extract" in sys.argv:
        idx = sys.argv.index("--extract")
        date_str = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        print(f"从深度研究提取预测 ({date_str or '今天'})...")
        predictions = extract_from_research(date_str)
        if predictions:
            committed = commit_predictions(predictions)
            print(f"已提交 {len(committed)} 条预测到追踪系统")
        else:
            print("无预测可提取。")

    elif "--report" in sys.argv:
        print(generate_report())

    elif "--verify-all" in sys.argv:
        due = check_due_predictions()
        print(f"到期预测: {len(due)} 条")
        for f in due:
            print(f"\n[{f['id']}] {f['prediction'][:100]}")
            print(f"  制定: {f['made_date']}, 应验日期: {f['verify_date']}")
            ans = input("  正确? (y/n/skip): ").strip().lower()
            if ans in ("y", "yes"):
                verify_prediction(f["id"], True, "手动确认")
            elif ans in ("n", "no"):
                verify_prediction(f["id"], False, "手动否认")
        print(f"\n验证完成。运行 --report 查看更新后的报告。")

    else:
        due = check_due_predictions()
        if due:
            print(f"到期待验证预测: {len(due)} 条")
            for f in due:
                print(f"  [{f['id']}] {f['prediction'][:80]}... (应验: {f['verify_date']})")
            print("\n使用 --verify-all 进行手动验证。")
        else:
            print("无到期预测。")
            print(generate_report().split("## 待验证预测")[0])


if __name__ == "__main__":
    main()
