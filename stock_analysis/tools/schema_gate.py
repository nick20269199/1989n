"""
schema_gate.py — 数据 Schema 门禁

每份 JSON 数据文件可以配一份 .schema.json 定义。
加载数据时或定时检查中校验字段类型/必需字段/保鲜时长。

用法:
    python tools/schema_gate.py                              # 全量校验所有数据文件
    python tools/schema_gate.py --file closing_review.json    # 单文件校验
    python tools/schema_gate.py --json                        # JSON 输出
"""
import json
import os
import sys
from datetime import datetime, time
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
SCHEMA_DIR = STOCK_DATA / "schemas"
ANALYSIS_DATA = Path("D:/1989n/stock_analysis/data")

# 文件路径解析规则: 有些文件在 stock_analysis/data/ 下
PATH_RULES = {
    "portfolio.json": str(ANALYSIS_DATA / "portfolio.json"),
    "portfolio.json.schema.json": str(ANALYSIS_DATA / "portfolio.json.schema.json"),
}


def _resolve_path(filename: str) -> Path:
    """按规则解析文件实际路径。"""
    if filename in PATH_RULES:
        return Path(PATH_RULES[filename])
    return STOCK_DATA / filename


def _load_schema(schema_path: Path) -> dict | None:
    """加载 schema 定义文件。"""
    if not schema_path.exists():
        return None
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_data_file(filepath: Path) -> any:
    """读取数据文件。"""
    if not filepath.exists():
        return None
    try:
        return json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _is_nullish(value) -> bool:
    """判断值是否为空/无效: None, 0, 0.0, '', [], {}。
    对于交易数据，0 价格/0 成交量通常意味着数据缺失。"""
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def validate_file(data_path: Path, schema: dict, skip_freshness: bool = False) -> list[dict]:
    """用 schema 校验一个数据文件，返回违规列表。"""
    issues = []
    data = _read_file_content(data_path, schema)
    if data is None:
        issues.append({"field": "_file", "type": "missing", "detail": "文件不存在或无法解析"})
        return issues

    required = schema.get("required_fields", [])
    field_types = schema.get("field_types", {})
    list_item_fields = schema.get("list_item_fields", {})
    min_rows = schema.get("min_rows", 0)
    freshness_hours = schema.get("freshness_hours", 0)
    non_null_fields = schema.get("non_null_fields", [])

    # ── 字典结构校验 ──
    if isinstance(data, dict):
        for field in required:
            if field not in data:
                issues.append({
                    "field": field, "type": "missing",
                    "detail": f"缺少必需字段: {field}",
                })
        for field, expected_type in field_types.items():
            if field in data:
                _check_type(field, data[field], expected_type, data_path, issues)
        # 空值检测 (non_null_fields)
        for field in non_null_fields:
            if field in data and _is_nullish(data[field]):
                issues.append({
                    "field": field, "type": "null_value",
                    "detail": f"关键字段 {field} 为空/零值 (数据可能缺失)",
                })

        # 嵌套列表项校验 (如 holdings、top、portfolio_auction)
        if list_item_fields.get("required_fields") or list_item_fields.get("field_types") \
           or list_item_fields.get("non_null_fields"):
            lr = list_item_fields.get("required_fields", [])
            lt = list_item_fields.get("field_types", {})
            ln = list_item_fields.get("non_null_fields", [])
            target_key = list_item_fields.get("list_key")  # 只校验指定 key 的列表
            for key in data:
                if target_key and key != target_key:
                    continue
                val = data[key]
                if isinstance(val, list):
                    for i, item in enumerate(val):
                        if isinstance(item, dict):
                            for f in lr:
                                if f not in item:
                                    issues.append({
                                        "field": f"[{i}].{f}", "type": "missing",
                                        "detail": f"第 {i+1} 条缺少字段: {f}",
                                    })
                            for f, et in lt.items():
                                if f in item:
                                    _check_type(f"[{i}].{f}", item[f], et, data_path, issues)
                            for f in ln:
                                if f in item and _is_nullish(item[f]):
                                    issues.append({
                                        "field": f"[{i}].{f}", "type": "null_value",
                                        "detail": f"第 {i+1} 条关键字段 {f} 为空/零值",
                                    })

    # ── 列表结构校验 ──
    elif isinstance(data, list):
        if min_rows and len(data) < min_rows:
            issues.append({
                "field": "_count", "type": "min_rows",
                "detail": f"期望 >= {min_rows} 行, 实际 {len(data)} 行",
            })
        for i, item in enumerate(data):
            if isinstance(item, dict):
                for f in required:
                    if f not in item:
                        issues.append({
                            "field": f"[{i}].{f}", "type": "missing",
                            "detail": f"第 {i+1} 条缺少字段: {f}",
                        })
                for f, et in field_types.items():
                    if f in item:
                        _check_type(f"[{i}].{f}", item[f], et, data_path, issues)
                for f in non_null_fields:
                    if f in item and _is_nullish(item[f]):
                        issues.append({
                            "field": f"[{i}].{f}", "type": "null_value",
                            "detail": f"第 {i+1} 条关键字段 {f} 为空/零值",
                        })
    else:
        issues.append({"field": "_root", "type": "unexpected_type",
                       "detail": f"顶层应为 dict 或 list, 实际 {type(data).__name__}"})

    # 保鲜检查
    if not skip_freshness and freshness_hours > 0 and data_path.exists():
        effective_hours = freshness_hours
        # 非交易时段(周末/盘前/盘后)自动翻倍阈值，减少误报
        now = datetime.now()
        is_weekend = now.weekday() >= 5
        is_outside_trade = now.time() < time(8, 30) or now.time() > time(15, 30)
        if is_weekend or is_outside_trade:
            effective_hours *= 2
        elapsed = (now - datetime.fromtimestamp(data_path.stat().st_mtime)).total_seconds()
        if elapsed > effective_hours * 3600:
            issues.append({
                "field": "_freshness",
                "type": "stale",
                "detail": f"超过 {freshness_hours}h 未更新 (已过 {elapsed/3600:.1f}h)",
            })

    return issues


def _read_file_content(data_path: Path, schema: dict) -> any:
    """读取文件内容，支持 'path_key' 和嵌套路径。"""
    return _read_data_file(data_path)


def _check_type(field_path: str, value: any, expected: str, data_path: Path, issues: list):
    """类型检查。"""
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "bool": bool,
        "list": list,
        "dict": dict,
        "any": None,
    }
    py_type = type_map.get(expected)
    if py_type and not isinstance(value, py_type):
        issues.append({
            "field": field_path,
            "type": "type_mismatch",
            "detail": f"应为 {expected}, 实际 {type(value).__name__} ({str(value)[:50]})",
        })


def scan_all() -> dict:
    """扫描 schemas/ 下所有定义，全量校验。"""
    if not SCHEMA_DIR.exists():
        return {"files_checked": 0, "passed": True, "violations": []}

    all_violations = []
    files_checked = 0

    for schema_file in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = _load_schema(schema_file)
        if not schema:
            continue

        files_patterns = schema.get("files", [])
        resolved_files = []

        for pattern in files_patterns:
            # 解析路径：可能是 stock_data/ 或 stock_analysis/data/
            resolved = _resolve_path(pattern)
            if "*" in pattern:
                # glob 模式
                search_dir = resolved.parent
                matches = list(search_dir.glob(resolved.name))
                resolved_files.extend(matches)
            elif resolved.exists():
                resolved_files.append(resolved)
            else:
                # 单个文件不存在 — 记录但不报错（可能是可选文件）
                pass

        if not resolved_files:
            continue

        freshness_latest_only = schema.get("freshness_latest_only", False)
        # Sort by mtime so latest_only picks the most recent
        if freshness_latest_only and len(resolved_files) > 1:
            resolved_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            latest = resolved_files[0]
            # Keep all files for validation, but only latest for freshness
            for data_path in resolved_files:
                issues = validate_file(data_path, schema, skip_freshness=(data_path != latest))
                if issues:
                    all_violations.append({
                        "file": data_path.name,
                        "issues": issues,
                    })
                files_checked += 1
        else:
            for data_path in resolved_files:
                issues = validate_file(data_path, schema)
                if issues:
                    all_violations.append({
                        "file": data_path.name,
                        "issues": issues,
                    })
                files_checked += 1

    return {
        "files_checked": files_checked,
        "passed": len(all_violations) == 0,
        "violations": all_violations,
    }


def validate_single_file(file_arg: str) -> dict:
    """校验单个数据文件（自动匹配 schema）。"""
    # 尝试直接文件名匹配
    schema_file = SCHEMA_DIR / f"{file_arg}.schema.json"
    if not schema_file.exists():
        # 尝试去掉后缀
        p = Path(file_arg)
        schema_file = SCHEMA_DIR / f"{p.stem}.schema.json"

    if not schema_file.exists():
        return {"file": file_arg, "error": "未找到 schema 定义"}

    schema = _load_schema(schema_file)
    if not schema:
        return {"file": file_arg, "error": "schema 文件无法解析"}

    data_path = _resolve_path(file_arg)
    if not data_path.exists():
        return {"file": file_arg, "error": "数据文件不存在"}

    issues = validate_file(data_path, schema)
    return {
        "file": file_arg,
        "passed": len(issues) == 0,
        "issues": issues,
    }


def main():
    as_json = "--json" in sys.argv

    # 检查是否有 --file 参数
    file_arg = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--file" and i + 1 < len(sys.argv) - 1:
            file_arg = sys.argv[i + 2]

    if file_arg:
        result = validate_single_file(file_arg)
    else:
        result = scan_all()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        if file_arg:
            if result.get("error"):
                print(f"[SCHEMA_GATE] {result['file']}: {result['error']}")
            elif result.get("passed"):
                print(f"[SCHEMA_GATE] {result['file']}: 通过")
            else:
                print(f"[SCHEMA_GATE] {result['file']}: 发现 {len(result['issues'])} 个问题")
                for iss in result["issues"]:
                    print(f"  ✗ {iss['field']}: {iss['detail']}")
        else:
            v = result.get("violations", [])
            if result["passed"]:
                print(f"[SCHEMA_GATE] 全部 {result['files_checked']} 个文件校验通过")
            else:
                print(f"[SCHEMA_GATE] {len(v)}/{result['files_checked']} 个文件有问题:")
                for v_item in v:
                    print(f"  ✗ {v_item['file']}: {len(v_item['issues'])} 个问题")
                    for iss in v_item["issues"][:3]:
                        print(f"    - {iss['field']}: {iss['detail']}")

    sys.exit(0 if result.get("passed", True) else 1)


if __name__ == "__main__":
    main()
