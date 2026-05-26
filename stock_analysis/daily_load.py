"""
daily_load.py — 晨间认知加载自动化

替代手动读文件/跑单行命令。单次调用输出完整结构化上下文。
用法:
    python daily_load.py                          # 正常模式
    python daily_load.py --brief                  # 简洁版（适合拼入报告）
    python daily_load.py --push-feishu            # 收件箱+蒸馏简报 推送飞书背调小队
"""
import json
import sys
from datetime import datetime
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
LEARNING_DIR = STOCK_DATA / "learning"
RULES_FILE = LEARNING_DIR / "rules.json"
QUESTIONS_FILE = LEARNING_DIR / "open_questions.json"
RATIO_BASELINES_FILE = LEARNING_DIR / "ratio_baselines.json"
DIGEST_DIR = LEARNING_DIR
INBOX_DIR = STOCK_DATA / "inbox"


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _latest_digest() -> dict:
    """取最新的非未来日期的摘要。"""
    today = datetime.now().strftime("%Y%m%d")
    files = sorted(DIGEST_DIR.glob("daily_digest_[0-9]*.json"), reverse=True)
    for f in files:
        # 提取日期部分（兼容 YYYYMMDD 和 YYYY-MM-DD 两种格式）
        fname = f.stem.replace("daily_digest_", "")
        fdate = fname.replace("-", "")
        if fdate <= today:
            return _load_json(f)
    return {}


def _active_rules() -> list[dict]:
    data = _load_json(RULES_FILE)
    rules = data.get("rules", [])
    return [r for r in rules if r.get("is_condensed")]


def _top_question() -> str:
    data = _load_json(QUESTIONS_FILE)
    items = data.get("items", [])
    open_items = [q for q in items if q.get("status") == "open"]
    if open_items:
        open_items.sort(key=lambda x: x.get("priority", 5))
        return open_items[0].get("question", "")
    return ""


def _ratio_alerts() -> list[str]:
    data = _load_json(RATIO_BASELINES_FILE)
    entries = data.get("entries", [])
    if not entries:
        return []
    latest = entries[-1]
    alerts = []
    for name, info in latest.get("ratios", {}).items():
        if info.get("alert") == "triggered":
            z = info.get("z_score", 0)
            alerts.append(f"{name}: z_score={z:+.2f}")
    return alerts


def _inbox_unprocessed() -> dict:
    """检查收件箱中未处理的条目数。"""
    counts = {}
    for fname in ["ideas.md", "links.md", "questions.md"]:
        path = INBOX_DIR / fname
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            unprocessed = [l for l in lines if "[processed]" not in l and l.strip()]
            counts[fname] = len(unprocessed)
        else:
            counts[fname] = 0
    # 图片
    img_dir = INBOX_DIR / "images"
    img_count = len(list(img_dir.glob("*"))) if img_dir.exists() else 0
    counts["images"] = img_count
    return counts


def load_context(brief: bool = False) -> dict:
    """获取完整晨间认知上下文。"""
    digest = _latest_digest()
    rules = _active_rules()
    alerts = _ratio_alerts()
    question = _top_question()
    inbox = _inbox_unprocessed()

    cycle = digest.get("cycle_stage", {})
    self_check = digest.get("self_check", {})

    ctx = {
        "loaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "digest_date": digest.get("date", ""),
        "cycle_stage": cycle.get("stage", "未知"),
        "cycle_confidence": cycle.get("confidence", 0),
        "strategy_hint": cycle.get("strategy_hint", ""),
        "next_risk": cycle.get("next_stage_risk", ""),
        "ratio_alerts": alerts,
        "collision_focus": digest.get("ratio_alerts", {}).get("collision_focus", ""),
        "rules_count": len(rules),
        "rules_today": digest.get("rules_today", []),
        "rules_latest": [{"condition": r.get("condition", ""), "action": r.get("action", "")}
                         for r in rules[-5:]],
        "expectation_gaps": digest.get("expectation_gaps", []),
        "self_check": {
            "mistake": self_check.get("mistake", ""),
            "mistake_root_cause": self_check.get("mistake_root_cause", ""),
            "ego_challenge": self_check.get("ego_challenge", ""),
        },
        "top_question": question,
        "inbox_unprocessed": inbox,
    }
    return ctx


def print_context(ctx: dict):
    """格式化为结构化输出。"""
    print(f"=== 晨间认知加载 v3 ===")
    print(f"周期阶段: {ctx['cycle_stage']} (置信度: {ctx['cycle_confidence']})")
    print(f"策略提示: {ctx['strategy_hint']}")
    print(f"下阶段风险: {ctx['next_risk']}")
    print()

    if ctx["digest_date"]:
        print(f"数据日期: {ctx['digest_date']}")

    if ctx["rules_today"]:
        print(f"\n昨日凝练规则({len(ctx['rules_today'])}条):")
        for r in ctx["rules_today"]:
            cond = r.get("condition", "")[:60]
            action = r.get("action", "")[:50]
            print(f"  - [{cond}] → {action}")

    if ctx["rules_count"]:
        print(f"规则库总计: {ctx['rules_count']} 条活跃规则")

    if ctx["ratio_alerts"]:
        print(f"\n比率警报({len(ctx['ratio_alerts'])}个):")
        for a in ctx["ratio_alerts"]:
            print(f"  - {a}")
    print(f"碰撞方向: {ctx['collision_focus']}")

    if ctx["expectation_gaps"]:
        print(f"\n预期差关注:")
        for g in ctx["expectation_gaps"]:
            print(f"  - {g.get('dimension','')}: 共识={g.get('consensus','')}")
            print(f"    → 偏差: {g.get('potential_gap','')}")

    sc = ctx["self_check"]
    if sc.get("mistake"):
        print(f"\n昨日错误避免: {sc['mistake'][:60]}...")
        print(f"  根因: {sc['mistake_root_cause']}")
    if sc.get("ego_challenge"):
        print(f"Ego Check: {sc['ego_challenge']}")

    if ctx["top_question"]:
        print(f"\n今日追踪问题: {ctx['top_question']}")

    inbox = ctx["inbox_unprocessed"]
    total_pending = sum(inbox.values())
    if total_pending > 0:
        print(f"\n📥 收件箱: 未处理 {total_pending} 项")
        for k, v in inbox.items():
            if v:
                print(f"  - {k}: {v} 条")

    print(f"\n=== 加载完成 ===")


def _read_inbox_content() -> dict:
    """读取收件箱中各文件的未处理条目内容。"""
    content = {}
    for fname in ["ideas.md", "links.md", "questions.md"]:
        path = INBOX_DIR / fname
        items = []
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                line = line.strip()
                if line and "[processed]" not in line and not line.startswith("#"):
                    items.append(line[:120])  # 截断过长行
        content[fname] = items
    img_dir = INBOX_DIR / "images"
    content["images"] = [p.name for p in img_dir.glob("*")[:5]] if img_dir.exists() else []
    return content


def _check_distillation_brief() -> str:
    """检查蒸馏简报，返回待处理摘要。"""
    brief_path = STOCK_DATA / "distillation_brief.md"
    if not brief_path.exists():
        return ""
    text = brief_path.read_text(encoding="utf-8")
    if "待蒸馏" not in text and "未处理" not in text:
        return ""
    return text[:500]


def push_to_feishu(ctx: dict):
    """推送收件箱和蒸馏简报到飞书背调小队。"""
    try:
        from feishu_sender import send_feishu_message
    except ImportError:
        print("[ERROR] feishu_sender 不可用，跳过推送")
        return

    inbox_content = _read_inbox_content()
    distill = _check_distillation_brief()

    # 组装内容
    sections = []
    sections.append(f"**周期阶段**: {ctx['cycle_stage']} ({ctx['cycle_confidence']})")
    sections.append(f"**规则库**: {ctx['rules_count']}条活跃")

    # 收件箱
    total = sum(len(v) for v in inbox_content.values())
    if total > 0:
        parts = [f"**收件箱待处理 ({total}项)**"]
        for fname, items in inbox_content.items():
            if items:
                label = fname.replace(".md", "")
                for item in items[:3]:  # 每类最多3条
                    parts.append(f"  · {item}")
                if len(items) > 3:
                    parts.append(f"  ... 还有{len(items)-3}条")
        sections.append("\n".join(parts))

    # 蒸馏简报
    if distill:
        sections.append(f"**蒸馏简报待处理**\n{distill[:300]}")

    title = f"晨间待处理 | {ctx['digest_date'] or '今日'}"
    ok = send_feishu_message(title, "\n\n".join(sections), chat_id="overnight")
    if ok:
        print(f"[飞书] 已推送至背调小队: {title}")
    else:
        print("[飞书] 推送失败")


def main():
    brief = "--brief" in sys.argv
    push = "--push-feishu" in sys.argv
    ctx = load_context(brief)

    if push:
        push_to_feishu(ctx)
        return

    if brief:
        print(f"[认知加载] {ctx['cycle_stage']} | {ctx['rules_count']}规则 | {len(ctx['ratio_alerts'])}警报 | 碰撞={ctx['collision_focus']}")
        return
    print_context(ctx)


if __name__ == "__main__":
    main()
