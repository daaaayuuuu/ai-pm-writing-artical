#!/usr/bin/env python3
"""Validate a Markdown article and its local PNG illustration package."""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path


IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
TOC_ITEM_RE = re.compile(r"^-\s+(.+?)\s*$", re.MULTILINE)
SPECIAL_HEADINGS = {"目录", "关键来源", "排版建议", "配图建议"}


def parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)[x×](\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError("尺寸必须写成 WIDTHxHEIGHT")
    return int(match.group(1)), int(match.group(2))


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", header[16:24])
    return None


def visible_character_count(markdown: str) -> int:
    text = re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)
    text = IMAGE_RE.sub("", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_`|\-]", "", text)
    return len(re.sub(r"\s+", "", text))


def resolve_image(article_path: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().split()[0]
    if target.startswith(("http://", "https://", "data:")):
        return None
    if target.startswith("sandbox:"):
        target = target.removeprefix("sandbox:")
    path = Path(target)
    if not path.is_absolute():
        path = article_path.parent / path
    return path


def toc_and_headings(markdown: str) -> tuple[list[str], list[str]]:
    headings = [heading.strip() for heading in H2_RE.findall(markdown)]
    body_headings = [heading for heading in headings if heading not in SPECIAL_HEADINGS]
    toc_match = re.search(
        r"^##\s+目录\s*$\n(.*?)(?=^##\s+|\Z)",
        markdown,
        re.MULTILINE | re.DOTALL,
    )
    toc_items = TOC_ITEM_RE.findall(toc_match.group(1)) if toc_match else []
    return toc_items, body_headings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("article", type=Path)
    parser.add_argument("--max-chars", type=int)
    parser.add_argument("--expect-images", type=int)
    parser.add_argument("--strict-dimensions", action="store_true")
    parser.add_argument("--cover-size", type=parse_size, default=(2048, 872))
    parser.add_argument("--body-size", type=parse_size, default=(2048, 1280))
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    try:
        markdown = args.article.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: 无法读取文章：{exc}")
        return 1

    count = visible_character_count(markdown)
    if args.max_chars and count > args.max_chars:
        errors.append(f"可见字符约 {count}，超过上限 {args.max_chars}")

    image_targets = IMAGE_RE.findall(markdown)
    if args.expect_images is not None and len(image_targets) != args.expect_images:
        errors.append(f"文章包含 {len(image_targets)} 张图，预期 {args.expect_images} 张")

    for index, raw_target in enumerate(image_targets):
        path = resolve_image(args.article, raw_target)
        if path is None:
            warnings.append(f"第 {index + 1} 张为远程图片，未检查本地文件")
            continue
        if not path.is_file():
            errors.append(f"第 {index + 1} 张图片不存在：{path}")
            continue
        size = png_size(path)
        if args.strict_dimensions and size:
            expected = args.cover_size if index == 0 else args.body_size
            if size != expected:
                errors.append(
                    f"第 {index + 1} 张尺寸为 {size[0]}x{size[1]}，"
                    f"预期 {expected[0]}x{expected[1]}"
                )
        elif args.strict_dimensions and size is None:
            warnings.append(f"第 {index + 1} 张不是可识别的 PNG，跳过尺寸检查")

    toc_items, headings = toc_and_headings(markdown)
    if "## 目录" in markdown and toc_items != headings:
        errors.append("目录与正文一级标题不一致")

    print(f"文章可见字符：{count}")
    print(f"Markdown 图片：{len(image_targets)}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("OK: 文章发布包基础检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
