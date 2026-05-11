"""
PPT 报告转飞书消息工具

将 PowerPoint (.pptx) 报告转换为飞书卡片消息并发送。

功能:
  - extract_ppt_content: 从每页幻灯片提取文本内容
  - format_ppt_to_feishu_card: 将幻灯片内容格式化为飞书卡片
  - send_ppt_report_to_feishu: 完整管道 (提取 → 格式化 → 发送)
  - extract_tables_from_ppt: 提取幻灯片中的表格数据

依赖:
  python-pptx: PPT 文件解析
  feishu_sender: 飞书消息发送

Usage:
  python ppt_to_feishu.py <ppt_path> [--dry-run]
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import STOCK_DATA_DIR, HEADERS

logger = logging.getLogger("ppt_to_feishu")

# python-pptx 检测
try:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.enum.text import PP_ALIGN
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False
    logger.warning("python-pptx 不可用，请安装: pip install python-pptx")


def _safe_len_shapes(slide) -> int:
    """安全获取幻灯片中 shapes 的数量。"""
    try:
        return len(slide.shapes)
    except Exception:
        return 0


def _safe_get_text(shape) -> str:
    """安全从 shape 中获取文本。"""
    try:
        if shape.has_text_frame:
            return shape.text_frame.text
    except Exception:
        pass
    try:
        if shape.has_table:
            return ""
    except Exception:
        pass
    return ""


def _rgb_to_hex(rgb) -> str | None:
    """将 pptx 的 RGBColor 转为 hex 字符串。"""
    try:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    except Exception:
        return None


# ============================================================
# 文本提取
# ============================================================

def _extract_slide_text(slide) -> dict:
    """
    从单页幻灯片提取结构化文本。

    Returns:
        dict: {
            "slide_number": int,
            "title": str,
            "bullets": list[str],
            "paragraphs": list[str],
            "formatted_runs": list[dict],
        }
    """
    slide_data: dict[str, Any] = {
        "slide_number": 0,
        "title": "",
        "bullets": [],
        "paragraphs": [],
        "formatted_runs": [],
    }

    try:
        slide_data["slide_number"] = slide.slide_number if hasattr(slide, "slide_number") else 0
    except Exception:
        pass

    if _safe_len_shapes(slide) == 0:
        return slide_data

    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue

        tf = shape.text_frame
        is_title = shape.is_placeholder and shape.placeholder_format.idx == 0

        for para in tf.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # 提取格式化信息 (bold, color, size)
            run_info: list[dict] = []
            for run in para.runs:
                if not run.text.strip():
                    continue
                info: dict[str, Any] = {"text": run.text}
                try:
                    font = run.font
                    if font.bold is not None:
                        info["bold"] = font.bold
                    if font.size is not None:
                        info["size_pt"] = round(font.size / 12700, 1)  # EMU to pt
                    if font.color and font.color.rgb:
                        info["color"] = _rgb_to_hex(font.color.rgb)
                except Exception:
                    pass
                run_info.append(info)

            if is_title and not slide_data["title"]:
                slide_data["title"] = text
            elif para.level is not None and para.level > 0:
                indent = "  " * para.level
                slide_data["bullets"].append(f"{indent}- {text}")
            else:
                slide_data["paragraphs"].append(text)

            if run_info:
                slide_data["formatted_runs"].extend(run_info)

    # 如果没找到 title 但第一段有内容，当做 title
    if not slide_data["title"] and slide_data["paragraphs"]:
        slide_data["title"] = slide_data["paragraphs"].pop(0)

    return slide_data


def extract_ppt_content(ppt_path: str) -> list[dict]:
    """
    从 PPT 文件中提取每页幻灯片的文本内容。

    Args:
        ppt_path: .pptx 文件路径

    Returns:
        list[dict]: 每页幻灯片的结构化内容，每个 dict 包含:
            - slide_number: 页码
            - title: 标题
            - bullets: 列表项
            - paragraphs: 段落文本
            - formatted_runs: 带格式的文本片段
    """
    if not PPTX_AVAILABLE:
        logger.error("python-pptx 不可用")
        return []

    ppt = Path(ppt_path)
    if not ppt.exists():
        logger.error(f"PPT 文件不存在: {ppt_path}")
        return []

    if ppt.suffix.lower() not in (".pptx",):
        logger.error(f"不支持的文件格式: {ppt.suffix} (仅支持 .pptx)")
        return []

    logger.info(f"解析 PPT: {ppt_path}")
    presentation = Presentation(str(ppt))

    slides: list[dict] = []
    total_slides = len(presentation.slides)
    logger.info(f"共 {total_slides} 页幻灯片")

    for slide in presentation.slides:
        slide_data = _extract_slide_text(slide)
        slides.append(slide_data)

    # 统计
    total_text = sum(
        len(" ".join(s.get("paragraphs", []) + s.get("bullets", [])))
        for s in slides
    )
    logger.info(f"提取完成: {len(slides)} 页, ~{total_text} 字符")

    return slides


# ============================================================
# 飞书卡片格式化
# ============================================================

# 飞书卡片单条消息最大字符限制
_FEISHU_CARD_MAX_CHARS = 20000
# 飞书消息最大发送条数 (防止超出 webhook 限制)
_FEISHU_CARD_MAX_SECTIONS = 50


def format_ppt_to_feishu_card(slides: list[dict]) -> dict:
    """
    将幻灯片内容格式化为飞书卡片消息结构。

    生成的卡片包含:
      - 标题: PPT 报告概览
      - 内容区块: 每页标题 + 摘要
      - 统计信息

    Args:
        slides: extract_ppt_content 返回的幻灯片列表

    Returns:
        dict: 飞书卡片消息 payload
    """
    if not slides:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "PPT 报告"},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "markdown", "content": "*PPT 文件为空或无内容*"}
                ],
            },
        }

    elements: list[dict] = []

    # 概览信息
    total_slides = len(slides)
    title_slides = [s for s in slides if s.get("title")]
    overview_lines = [
        f"**总页数**: {total_slides}",
        f"**含标题页**: {len(title_slides)}",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    elements.append({
        "tag": "markdown",
        "content": "### 概览\n" + "\n".join(overview_lines),
    })

    # 分隔线
    elements.append({"tag": "hr", "content": ""})

    # 每页幻灯片的标题和第一段内容
    char_count = 0
    section_count = 0
    for slide in slides:
        if section_count >= _FEISHU_CARD_MAX_SECTIONS:
            elements.append({
                "tag": "markdown",
                "content": f"... *(还有 {total_slides - section_count} 页未显示)*",
            })
            break

        num = slide.get("slide_number", "?")
        title = slide.get("title", "")

        # 构建该页内容
        parts: list[str] = []
        if title:
            parts.append(f"**第{num}页: {title}**")
        else:
            parts.append(f"**第{num}页**")

        # 添加正文 (限制长度)
        paragraphs = slide.get("paragraphs", [])
        bullets = slide.get("bullets", [])

        content_text = ""
        for p in paragraphs[:3]:
            content_text += p[:200] + "\n"
        for b in bullets[:5]:
            content_text += b[:200] + "\n"

        if content_text.strip():
            parts.append(content_text.strip())

        section_text = "\n".join(parts)
        if char_count + len(section_text) > _FEISHU_CARD_MAX_CHARS:
            elements.append({
                "tag": "markdown",
                "content": f"... *(内容超长，已截断，还有 {total_slides - section_count} 页)*",
            })
            break

        elements.append({"tag": "markdown", "content": section_text})
        char_count += len(section_text)
        section_count += 1

    # 页脚
    elements.append({"tag": "hr", "content": ""})
    elements.append({
        "tag": "note",
        "content": "由 PPT 报告自动转换生成",
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "PPT 报告"},
                "template": "blue",
            },
            "elements": elements,
        },
    }


def _convert_to_feishu_elements(slides: list[dict]) -> list[dict]:
    """将幻灯片列表转为飞书卡片元素列表 (供 send_feishu_card 使用)。"""
    elements: list[dict] = [{"tag": "markdown", "content": "### 报告内容"}]
    for i, slide in enumerate(slides[:30]):
        title = slide.get("title", "")
        content = "\n".join(slide.get("paragraphs", [])[:2])
        text = f"**{i+1}. {title}**\n{content}" if title else f"**{i+1}.** {content}"
        if text.strip():
            elements.append({"tag": "markdown", "content": text})
    return elements


def send_ppt_report_to_feishu(ppt_path: str) -> bool:
    """
    完整管道: 提取 PPT 内容 → 格式化为飞书卡片 → 发送。

    Args:
        ppt_path: .pptx 文件路径

    Returns:
        bool: 发送是否成功
    """
    logger.info(f"PPT 报告转飞书: {ppt_path}")

    # Step 1: 提取内容
    slides = extract_ppt_content(ppt_path)
    if not slides:
        logger.error("PPT 内容为空")
        return False

    # Step 2: 格式化卡片
    card = format_ppt_to_feishu_card(slides)

    # Step 3: 保存到本地 (备用)
    STOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    ppt_name = Path(ppt_path).stem
    json_path = STOCK_DATA_DIR / f"ppt_{ppt_name}_content.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(slides, f, ensure_ascii=False, indent=2)
    logger.info(f"PPT 内容已保存: {json_path}")

    # Step 4: 通过 feishu_sender 发送
    try:
        from feishu_sender import send_feishu_card, _post_to_feishu

        # 使用 card 格式发送
        title = f"PPT: {ppt_name}"
        sections: list[dict] = _convert_to_feishu_elements(slides)

        # 直接用 _post_to_feishu 发送完整卡片
        ok = _post_to_feishu(card)
        if ok:
            logger.info(f"PPT 报告已发送到飞书: {ppt_name}")
        else:
            logger.warning("飞书卡片发送失败，尝试分段发送...")
            # 回退: 使用 send_feishu_card 发简化版
            ok = send_feishu_card(title, sections)

        return ok
    except ImportError:
        logger.warning("feishu_sender 模块不可用，内容已保存到本地 JSON")
        return False
    except Exception as e:
        logger.error(f"发送飞书消息失败: {e}")
        return False


# ============================================================
# 表格提取
# ============================================================

def extract_tables_from_ppt(ppt_path: str) -> list[list[list[str]]]:
    """
    从 PPT 中提取所有表格。

    遍历所有幻灯片，提取其中的表格数据。

    Args:
        ppt_path: .pptx 文件路径

    Returns:
        list[list[list[str]]]: 各页表格，每个表格是二维字符串数组
        [
            [  # 第1个表格
                ["表头1", "表头2", ...],
                ["数据1", "数据2", ...],
            ],
            ...
        ]
    """
    if not PPTX_AVAILABLE:
        logger.error("python-pptx 不可用")
        return []

    ppt = Path(ppt_path)
    if not ppt.exists():
        logger.error(f"PPT 文件不存在: {ppt_path}")
        return []

    logger.info(f"提取 PPT 表格: {ppt_path}")
    presentation = Presentation(str(ppt))

    all_tables: list[list[list[str]]] = []
    for slide_idx, slide in enumerate(presentation.slides):
        for shape in slide.shapes:
            if not shape.has_table:
                continue
            table = shape.table
            table_data: list[list[str]] = []
            for row in table.rows:
                row_data: list[str] = []
                for cell in row.cells:
                    # 清理单元格文本
                    text = cell.text.strip().replace("\n", " ").replace("\r", "")
                    row_data.append(text)
                # 跳过全空行
                if any(cell for cell in row_data):
                    table_data.append(row_data)

            if table_data:
                all_tables.append(table_data)
                logger.info(
                    f"  第{slide_idx+1}页 表格: "
                    f"{len(table_data)}行 x {len(table_data[0]) if table_data else 0}列"
                )

    logger.info(f"共找到 {len(all_tables)} 个表格")
    return all_tables


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    """命令行入口: 传入 .pptx 文件路径，提取并发送到飞书。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if len(sys.argv) < 2:
        print("用法:")
        print("  python ppt_to_feishu.py <ppt_path>          # 提取并发送到飞书")
        print("  python ppt_to_feishu.py <ppt_path> --dry-run # 仅提取不发送")
        print("  python ppt_to_feishu.py <ppt_path> --tables  # 仅提取表格")
        sys.exit(1)

    ppt_path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    tables_only = "--tables" in sys.argv

    if tables_only:
        tables = extract_tables_from_ppt(ppt_path)
        if tables:
            print(f"\n找到 {len(tables)} 个表格:\n")
            for i, table in enumerate(tables):
                print(f"--- 表格 {i+1} ({len(table)}行 x {len(table[0]) if table else 0}列) ---")
                for row in table[:10]:
                    print(" | ".join(row))
                if len(table) > 10:
                    print(f"  ... (还有 {len(table) - 10} 行)")
                print()
        else:
            print("未找到表格")
        return

    if dry_run:
        slides = extract_ppt_content(ppt_path)
        if slides:
            print(f"\n提取 {len(slides)} 页幻灯片:\n")
            for s in slides:
                num = s.get("slide_number", "?")
                title = s.get("title", "(无标题)")
                paras = s.get("paragraphs", [])
                bullets = s.get("bullets", [])
                print(f"  第{num}页: {title}")
                for p in paras[:3]:
                    print(f"    {p[:120]}")
                for b in bullets[:3]:
                    print(f"    {b[:120]}")
                print()
        else:
            print("未提取到内容")
        return

    # 正常流程: 提取并发送
    ok = send_ppt_report_to_feishu(ppt_path)
    if ok:
        print("PPT 报告已发送到飞书")
    else:
        print("发送失败，请检查日志")
        sys.exit(1)


if __name__ == "__main__":
    main()
