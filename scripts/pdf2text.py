#!/usr/bin/env python3
# ============================================================
# pdf2text.py — PDF 简历 → 纯文本提取
#
# 纯 Python 实现,唯一的第三方依赖是 pypdf(纯 Python、零传递依赖、约 2MB),
# 用于替代系统级的 pdftotext(poppler),方便开源分发。
# 仅提取文字,不做分析;Markdown 包装由工作流后续完成。
#
# 用法:
#   python3 scripts/pdf2text.py <PDF文件> [输出文件]
#   不传输出文件时,文本打印到标准输出。
#
# 安装依赖(全项目只有这一个 pip 依赖):
#   pip install pypdf
# ============================================================
import argparse
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit("错误:缺少依赖 pypdf。请先安装:pip install pypdf")


def clean_text(text: str) -> str:
    """对提取出的文本做轻量清理,不做重排:
    - 统一换行符、去掉行尾空格;
    - 折叠连续空行(3 行以上 → 1 行),保留原有段落结构。
    """
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank <= 1:  # 连续空行只保留一个
                out.append("")
        else:
            blank = 0
            out.append(line)
    return "\n".join(out).strip() + "\n"


def extract_text(pdf: Path) -> str:
    """逐页提取文本并合并。优先用 layout 模式(保留分栏/缩进),
    旧版 pypdf 不支持时自动回退到普通模式。
    """
    reader = PdfReader(str(pdf))
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text(extraction_mode="layout")
        except TypeError:  # 旧版 pypdf 无 extraction_mode 参数
            text = page.extract_text()
        pages.append(text or "")
    return "\n\n".join(pages)


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF → 纯文本提取(pypdf)")
    parser.add_argument("pdf", help="PDF 文件路径")
    parser.add_argument("output", nargs="?", help="输出文件路径(省略则打印到标准输出)")
    args = parser.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        sys.exit(f"错误:找不到 PDF 文件 {pdf}")

    text = clean_text(extract_text(pdf))
    if not text.strip():
        sys.exit("错误:未能从该 PDF 提取出文字。若为扫描/图片型 PDF,需先用 OCR 识别。")

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"已保存:{args.output}", file=sys.stderr)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
