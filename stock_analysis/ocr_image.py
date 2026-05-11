"""
OCR 图片文字提取工具

支持:
  - 图片文件 OCR (ocr_image)
  - 屏幕截图 OCR (ocr_screenshot)
  - PDF 页面 OCR (ocr_pdf_page)

OCR 引擎优先级:
  1. rapidocr (轻量级，中文准确率高)
  2. pytesseract (备选)
  3. 百炼 qwen-vl-max API (云端 OCR，最高精度)

Usage:
  python ocr_image.py <image_path>
  python ocr_image.py screenshot
  python ocr_image.py pdf <pdf_path> <page_number>
"""

import logging
import os
import sys
from pathlib import Path

from config import STOCK_DATA_DIR

logger = logging.getLogger("ocr_image")

# === OCR 引擎检测 ===

_RAPIDOCR_AVAILABLE = False
_PYTESSERACT_AVAILABLE = False
_PILLOW_AVAILABLE = False
_FITZ_AVAILABLE = False      # PyMuPDF
_PYSCREENSHOT_AVAILABLE = False

try:
    from rapidocr import RapidOCR
    _RAPIDOCR_AVAILABLE = True
except ImportError:
    pass

try:
    import pytesseract
    _PYTESSERACT_AVAILABLE = True
except ImportError:
    pass

try:
    from PIL import Image
    _PILLOW_AVAILABLE = True
except ImportError:
    pass

try:
    import fitz  # PyMuPDF
    _FITZ_AVAILABLE = True
except ImportError:
    pass

try:
    import mss
    _PYSCREENSHOT_AVAILABLE = True
except ImportError:
    pass


def _ocr_with_rapidocr(image_input) -> str:
    """使用 rapidocr 进行 OCR (中文优化)。"""
    engine = RapidOCR()
    result, _ = engine(image_input)
    if not result:
        return ""
    lines: list[str] = []
    for item in result:
        text = str(item[1])
        confidence = float(item[2])
        if text.strip():
            lines.append(text)
    return "\n".join(lines)


def _ocr_with_tesseract(image_input) -> str:
    """使用 pytesseract 进行 OCR。"""
    if not _PILLOW_AVAILABLE:
        logger.error("Pillow 不可用")
        return ""

    # 确保输入是 PIL Image
    if isinstance(image_input, (str, Path)):
        img = Image.open(str(image_input))
    elif isinstance(image_input, Image.Image):
        img = image_input
    else:
        img = Image.fromarray(image_input)

    # 预处理: 转灰度 + 二值化提升识别率
    try:
        img = img.convert("L")
        # 二值化: 阈值 127
        img = img.point(lambda x: 0 if x < 127 else 255, "1")
    except Exception:
        pass  # 预处理失败，用原图

    try:
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        return text.strip()
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract 未安装，请安装 tesseract-ocr")
        return "[错误] Tesseract 未安装"
    except Exception as e:
        logger.error(f"Tesseract OCR 失败: {e}")
        return ""


def _ocr_with_vision_api(image_path: str) -> str:
    """使用百炼 qwen-vl-max API 进行云端 OCR。"""
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not api_key:
        logger.warning("ANTHROPIC_AUTH_TOKEN 未配置，跳过云端 OCR")
        return ""

    try:
        from vision import extract_text_from_image
        return extract_text_from_image(image_path)
    except ImportError:
        logger.warning("vision 模块不可用，跳过云端 OCR")
        return ""


# ============================================================
# 公共 API
# ============================================================

def ocr_image(image_path: str) -> str:
    """
    从图片文件中提取文字。

    引擎优先级: rapidocr > pytesseract > 云端 API

    Args:
        image_path: 图片文件路径

    Returns:
        str: 识别到的文字
    """
    path = Path(image_path)
    if not path.exists():
        logger.error(f"图片文件不存在: {image_path}")
        return ""

    logger.info(f"OCR 识别: {image_path}")

    # 优先使用 rapidocr (中文优化)
    if _RAPIDOCR_AVAILABLE:
        try:
            text = _ocr_with_rapidocr(str(path))
            if text.strip():
                logger.info(f"rapidocr 识别完成: {len(text)} 字符")
                return text
        except Exception as e:
            logger.warning(f"rapidocr 失败: {e}")

    # 备选: pytesseract
    if _PYTESSERACT_AVAILABLE and _PILLOW_AVAILABLE:
        try:
            text = _ocr_with_tesseract(str(path))
            if text.strip():
                logger.info(f"tesseract 识别完成: {len(text)} 字符")
                return text
        except Exception as e:
            logger.warning(f"tesseract 失败: {e}")

    # 最后备选: 云端 API
    text = _ocr_with_vision_api(str(path))
    if text.strip():
        return text

    logger.error("所有 OCR 引擎均不可用")
    return "[错误] 无可用的 OCR 引擎。请安装: pip install rapidocr"


def ocr_screenshot(region: tuple = None) -> str:
    """
    截取屏幕指定区域并进行 OCR 识别。

    Args:
        region: 截屏区域 (left, top, width, height)，None 表示全屏

    Returns:
        str: 识别到的文字
    """
    logger.info("屏幕截图 OCR")

    if not _PYSCREENSHOT_AVAILABLE:
        # 回退: 使用 PIL.ImageGrab
        try:
            from PIL import ImageGrab
        except ImportError:
            logger.error("截图需要 Pillow 库: pip install Pillow")
            return "[错误] 截图功能不可用。请安装: pip install Pillow mss"

        if region:
            img = ImageGrab.grab(bbox=region)
        else:
            img = ImageGrab.grab()
    else:
        with mss.mss() as sct:
            if region:
                left, top, width, height = region
                monitor = {"left": left, "top": top, "width": width, "height": height}
            else:
                monitor = sct.monitors[1]  # 主显示器
            screenshot = sct.grab(monitor)
            from PIL import Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    # 保存截图
    screenshot_dir = STOCK_DATA_DIR / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    import time
    ts = time.strftime("%Y%m%d_%H%M%S")
    screenshot_path = screenshot_dir / f"ocr_screenshot_{ts}.png"
    img.save(str(screenshot_path))
    logger.info(f"截图已保存: {screenshot_path}")

    # OCR 识别
    return ocr_image(str(screenshot_path))


def ocr_pdf_page(pdf_path: str, page: int) -> str:
    """
    对 PDF 的指定页面进行 OCR 识别。

    需要 PyMuPDF (fitz) 将 PDF 页面渲染为图片。

    Args:
        pdf_path: PDF 文件路径
        page: 页码 (从 0 开始)

    Returns:
        str: 识别到的文字
    """
    pdf = Path(pdf_path)
    if not pdf.exists():
        logger.error(f"PDF 文件不存在: {pdf_path}")
        return ""

    logger.info(f"OCR PDF 页面: {pdf_path} 第{page}页")

    if not _FITZ_AVAILABLE:
        logger.error("PyMuPDF (fitz) 不可用，请安装: pip install PyMuPDF")
        return "[错误] PyMuPDF 未安装，请执行: pip install PyMuPDF"

    # 特殊处理: pytesseract 可以直接 OCR PDF
    if _PYTESSERACT_AVAILABLE and _PILLOW_AVAILABLE:
        try:
            from PIL import Image
            doc = fitz.open(str(pdf))
            if page >= doc.page_count:
                logger.error(f"页码超出范围: {page} (共{doc.page_count}页)")
                return ""
            page_obj = doc[page]
            # 渲染为图片 (DPI=200 保证清晰度)
            pix = page_obj.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()
            text = _ocr_with_tesseract(img)
            if text.strip():
                logger.info(f"PDF OCR 完成 (tesseract): {len(text)} 字符")
                return text
        except Exception as e:
            logger.warning(f"PDF tesseract OCR 失败: {e}")

    # 回退: 渲染为图片后用 rapidocr
    try:
        from PIL import Image
        doc = fitz.open(str(pdf))
        if page >= doc.page_count:
            logger.error(f"页码超出范围: {page} (共{doc.page_count}页)")
            return ""
        page_obj = doc[page]
        pix = page_obj.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()

        if _RAPIDOCR_AVAILABLE:
            text = _ocr_with_rapidocr(img)
            if text.strip():
                logger.info(f"PDF OCR 完成 (rapidocr): {len(text)} 字符")
                return text

        # 保存图片备用
        tmp_dir = STOCK_DATA_DIR / "pdf_pages"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"{pdf.stem}_p{page}.png"
        img.save(str(tmp_path))
        logger.info(f"PDF 页面已渲染: {tmp_path}")

        # 尝试云端 OCR
        return _ocr_with_vision_api(str(tmp_path)) or ""

    except Exception as e:
        logger.error(f"PDF OCR 失败: {e}")
        return ""


# ============================================================
# 主入口
# ============================================================

def main() -> None:
    """命令行入口: 传入图片/PDF 路径或 screenshot 命令进行 OCR。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if len(sys.argv) < 2:
        print("用法:")
        print("  python ocr_image.py <image_path>      # OCR 图片文件")
        print("  python ocr_image.py screenshot         # 截屏并 OCR")
        print("  python ocr_image.py pdf <pdf_path> <page>  # OCR PDF 指定页面")
        print()
        print("依赖 (按优先级):")
        print("  rapidocr (推荐, 中文优化)")
        print("  pytesseract + tesseract-ocr")
        print("  百炼 qwen-vl-max API (需 ANTHROPIC_AUTH_TOKEN)")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "screenshot":
        text = ocr_screenshot()
    elif command == "pdf":
        if len(sys.argv) < 4:
            print("用法: python ocr_image.py pdf <pdf_path> <page_number>")
            sys.exit(1)
        pdf_path = sys.argv[2]
        try:
            page = int(sys.argv[3])
        except ValueError:
            page = 0
        text = ocr_pdf_page(pdf_path, page)
    else:
        text = ocr_image(sys.argv[1])

    print()
    print("=" * 60)
    print(text if text else "(未识别到文字)")
    print("=" * 60)


if __name__ == "__main__":
    main()
