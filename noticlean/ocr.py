from __future__ import annotations

from io import BytesIO


class OCRUnavailableError(RuntimeError):
    pass


def ocr_image(image_bytes: bytes, lang: str = "chi_sim+eng") -> str:
    if not image_bytes:
        raise OCRUnavailableError("截图内容为空，请重新上传。")
    try:
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError as error:
        raise OCRUnavailableError("尚未安装可选 OCR 依赖，请安装 requirements-ocr.txt，或直接粘贴通知文本。") from error
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            return pytesseract.image_to_string(image, lang=lang).strip()
    except pytesseract.TesseractNotFoundError as error:
        raise OCRUnavailableError("未找到 Tesseract，请安装程序及 chi_sim 中文语言包，或直接粘贴通知文本。") from error
    except pytesseract.TesseractError as error:
        raise OCRUnavailableError("OCR 识别失败，请确认已安装 chi_sim 中文语言包，并检查截图是否清晰。") from error
    except (OSError, ValueError) as error:
        raise OCRUnavailableError("无法读取这张截图，请更换 PNG/JPG 图片或直接粘贴通知文本。") from error
