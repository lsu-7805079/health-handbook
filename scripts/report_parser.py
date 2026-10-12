from __future__ import annotations

from functools import lru_cache
import io
import re
from typing import Any

import pymupdf
import numpy as np
from PIL import Image
from pypdf import PdfReader
MAX_PDF_PAGES = 30


@lru_cache(maxsize=1)
def get_ocr_engine() -> Any:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "当前云端环境暂不支持图片 OCR。请上传包含可复制文字的 PDF，"
            "或先在本地完成脱敏后粘贴报告文本。"
        ) from exc
    return RapidOCR()


def ocr_image(image: Image.Image) -> str:
    rgb_image = image.convert("RGB")
    result, _ = get_ocr_engine()(np.asarray(rgb_image))
    if not result:
        return ""
    return "\n".join(str(item[1]) for item in result if len(item) >= 2).strip()


def extract_image_text(file_bytes: bytes) -> dict[str, Any]:
    with Image.open(io.BytesIO(file_bytes)) as image:
        text = ocr_image(image)
    return {"text": text, "method": "图片 OCR", "pages": 1, "warnings": []}


def extract_pdf_text(file_bytes: bytes) -> dict[str, Any]:
    reader = PdfReader(io.BytesIO(file_bytes))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("PDF 已加密，请先解除密码后再上传。") from exc

    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise ValueError(f"PDF 共 {page_count} 页，当前最多处理 {MAX_PDF_PAGES} 页。")

    direct_pages: list[str] = []
    ocr_page_indexes: list[int] = []
    for index, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        direct_pages.append(text)
        if len(re.sub(r"\s+", "", text)) < 20:
            ocr_page_indexes.append(index)

    if ocr_page_indexes:
        document = pymupdf.open(stream=file_bytes, filetype="pdf")
        for index in ocr_page_indexes:
            page = document.load_page(index)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            direct_pages[index] = ocr_image(image)
        document.close()

    warnings = []
    if ocr_page_indexes:
        warnings.append(f"第 {', '.join(str(i + 1) for i in ocr_page_indexes)} 页使用了 OCR，请重点核对数值。")
    method = "PDF 文本提取" if not ocr_page_indexes else "PDF 文本提取 + OCR"
    text = "\n\n".join(
        f"--- 第 {index + 1} 页 ---\n{page_text}"
        for index, page_text in enumerate(direct_pages)
        if page_text
    )
    return {"text": text, "method": method, "pages": page_count, "warnings": warnings}


def extract_report(file_bytes: bytes, suffix: str) -> dict[str, Any]:
    suffix = suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(file_bytes)
    if suffix in {".jpg", ".jpeg", ".png"}:
        return extract_image_text(file_bytes)
    raise ValueError("不支持的文件类型。请上传 PDF、JPG、JPEG 或 PNG。")


def find_common_indicators(text: str) -> list[dict[str, str]]:
    patterns = [
        ("血压", r"(?<!\d)(\d{2,3})\s*/\s*(\d{2,3})(?!\d)", "mmHg"),
        ("空腹血糖", r"(?:空腹血糖|葡萄糖)\D{0,12}(\d+(?:\.\d+)?)", "以报告为准"),
        ("糖化血红蛋白", r"(?:糖化血红蛋白|HbA1c)\D{0,12}(\d+(?:\.\d+)?)", "%"),
        ("总胆固醇", r"(?:总胆固醇|TC)\D{0,12}(\d+(?:\.\d+)?)", "以报告为准"),
        ("甘油三酯", r"(?:甘油三酯|TG)\D{0,12}(\d+(?:\.\d+)?)", "以报告为准"),
        ("低密度脂蛋白", r"(?:低密度脂蛋白(?:胆固醇)?|LDL-C?)\D{0,12}(\d+(?:\.\d+)?)", "以报告为准"),
        ("高密度脂蛋白", r"(?:高密度脂蛋白(?:胆固醇)?|HDL-C?)\D{0,12}(\d+(?:\.\d+)?)", "以报告为准"),
        ("尿酸", r"(?:尿酸|UA)\D{0,12}(\d+(?:\.\d+)?)", "以报告为准"),
        ("BMI", r"(?:BMI|体质指数)\D{0,12}(\d+(?:\.\d+)?)", "kg/m²"),
    ]
    indicators: list[dict[str, str]] = []
    for name, pattern, unit in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = "/".join(match.groups()) if len(match.groups()) > 1 else match.group(1)
        indicators.append({"指标": name, "识别值": value, "单位": unit, "状态": "待核对"})
    return indicators


SENSITIVE_PATTERNS = [
    ("身份证号", r"(?<!\d)\d{17}[\dXx](?!\d)", "[身份证号已隐藏]"),
    ("手机号", r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已隐藏]"),
    (
        "病历号",
        r"((?:病历号|门诊号|住院号)\s*[:：]?\s*)[A-Za-z0-9-]{4,}",
        r"\1[已隐藏]",
    ),
    (
        "姓名",
        r"((?:姓名|患者姓名)\s*[:：]?\s*)[\u4e00-\u9fff·]{2,8}",
        r"\1[已隐藏]",
    ),
    (
        "住址",
        r"((?:家庭住址|联系地址|住址)\s*[:：]?\s*)[^\n]{4,60}",
        r"\1[已隐藏]",
    ),
]


def detect_sensitive_data(text: str) -> list[str]:
    return [label for label, pattern, _ in SENSITIVE_PATTERNS if re.search(pattern, text)]


def redact_sensitive_data(text: str) -> tuple[str, list[str]]:
    redacted = text
    findings: list[str] = []
    for label, pattern, replacement in SENSITIVE_PATTERNS:
        if re.search(pattern, redacted):
            findings.append(label)
            redacted = re.sub(pattern, replacement, redacted)
    return redacted, findings
