"""测试知识库文档解析服务。"""
import os
import re
from typing import Optional


SUPPORTED_TEXT_TYPES = {"text/plain", "text/markdown", "application/markdown"}
SUPPORTED_PDF_TYPES = {"application/pdf"}
SUPPORTED_DOCX_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}
SUPPORTED_XLSX_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
}
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


def _get_file_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def parse_text(content: bytes) -> str:
    """解析纯文本 / Markdown。"""
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def parse_pdf(content: bytes) -> str:
    """解析 PDF，优先使用 pypdf，回退到 PyPDF2。"""
    try:
        from pypdf import PdfReader
        from io import BytesIO
        reader = PdfReader(BytesIO(content))
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        return "\n".join(texts)
    except Exception:
        pass

    try:
        from PyPDF2 import PdfReader
        from io import BytesIO
        reader = PdfReader(BytesIO(content))
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        return "\n".join(texts)
    except Exception as exc:
        raise RuntimeError(f"PDF 解析失败：{exc}")


def parse_docx(content: bytes) -> str:
    """解析 Word 文档。"""
    try:
        from docx import Document
        from io import BytesIO
        doc = Document(BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as exc:
        raise RuntimeError(f"DOCX 解析失败：{exc}")


def parse_xlsx(content: bytes) -> str:
    """解析 Excel 表格，转换为 Markdown 表格文本，便于 AI 理解和检索。"""
    try:
        from openpyxl import load_workbook
        from io import BytesIO

        wb = load_workbook(BytesIO(content), data_only=True)
        parts = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            parts.append(f"## 工作表：{sheet_name}")

            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                parts.append("（空表）")
                continue

            # 表头
            header = rows[0]
            parts.append("| " + " | ".join(str(c or "") for c in header) + " |")
            parts.append("| " + " | ".join("---" for _ in header) + " |")

            # 数据行
            for row in rows[1:]:
                # 跳过完全空行
                if not any(cell is not None and str(cell).strip() for cell in row):
                    continue
                parts.append("| " + " | ".join(str(c or "") for c in row) + " |")

            parts.append("")

        return "\n".join(parts)
    except Exception as exc:
        raise RuntimeError(f"XLSX 解析失败：{exc}")


def parse_image(content: bytes, filename: str) -> str:
    """解析图片，优先使用 OCR，未安装依赖时返回提示。"""
    try:
        from PIL import Image
        import pytesseract
        from io import BytesIO
        image = Image.open(BytesIO(content))
        return pytesseract.image_to_string(image, lang="chi_sim+eng")
    except Exception as exc:
        raise RuntimeError(f"图片 OCR 解析失败：{exc}")


def parse_document(content: bytes, filename: str, content_type: Optional[str] = None) -> str:
    """根据文件类型选择解析器。"""
    ext = _get_file_extension(filename)

    if ext in {".txt", ".md", ".markdown"}:
        return parse_text(content)

    if ext == ".pdf":
        return parse_pdf(content)

    if ext == ".docx":
        return parse_docx(content)

    if ext in {".xlsx", ".xls"}:
        return parse_xlsx(content)

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return parse_image(content, filename)

    # 根据 content_type 兜底
    if content_type:
        if content_type in SUPPORTED_TEXT_TYPES or content_type.startswith("text/"):
            return parse_text(content)
        if content_type in SUPPORTED_PDF_TYPES:
            return parse_pdf(content)
        if content_type in SUPPORTED_DOCX_TYPES:
            return parse_docx(content)
        if content_type in SUPPORTED_XLSX_TYPES:
            return parse_xlsx(content)
        if content_type in SUPPORTED_IMAGE_TYPES:
            return parse_image(content, filename)

    raise RuntimeError(f"不支持的文件类型：{ext or content_type}")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
    """将文本分片，用于检索。"""
    if not text:
        return []

    # 按段落和句子简单拆分，避免截断
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) > chunk_size:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}".strip()

    if current:
        chunks.append(current.strip())

    # 如果单段过长，再按句子切分
    result = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            result.append(chunk)
            continue
        sentences = re.split(r"(?<=[。！？.!?])\s+", chunk)
        temp = ""
        for s in sentences:
            if len(temp) + len(s) > chunk_size:
                result.append(temp.strip())
                temp = s
            else:
                temp = f"{temp}{s}"
        if temp:
            result.append(temp.strip())

    return result
