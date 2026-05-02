import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

SCRIPT_PATH = Path(os.environ.get("NEWS_SCRIPT_PATH", "input/news_script.txt"))
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
EXECUTABLE_CANDIDATES = {
    "ffmpeg": ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"],
    "ffprobe": ["/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"],
}


@dataclass
class NewsItem:
    headline: str
    source: str
    visual: str
    script: str
    takeaway: str
    facts: list[str]
    keywords: list[str]
    watch: str
    section: str


@dataclass
class NewsSection:
    name: str
    intro: str
    items: list[NewsItem]


@dataclass
class NewsScript:
    title: str
    subtitle: str
    date: str
    opening: str
    closing: str
    sections: list[NewsSection]
    raw_text: str
    legacy_mode: bool = False


def read_script_file(path: Path = SCRIPT_PATH) -> str:
    return path.read_text(encoding="utf-8").strip()


def normalize_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, list):
        return [normalize_sentence(str(v)) for v in values if str(v).strip()]
    return [normalize_sentence(str(values))]


def split_sentences(text: str, max_len: int = 24) -> list[str]:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[。！？!?\.])\s*", text)
    parts = [p.strip() for p in parts if p.strip()]

    lines = []
    for part in parts:
        if len(part) <= max_len:
            lines.append(part)
            continue
        if " " not in part:
            chunks = [part[i : i + max_len] for i in range(0, len(part), max_len)]
            lines.extend(chunks)
            continue

        words = part.split(" ")
        current = ""
        for word in words:
            trial = word if not current else f"{current} {word}"
            if len(trial) <= max_len:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def load_news_script(path: Path = SCRIPT_PATH) -> NewsScript:
    raw_text = read_script_file(path)
    if raw_text.startswith("{"):
        return _load_json_script(raw_text)
    return _load_legacy_script(raw_text)


def _load_json_script(raw_text: str) -> NewsScript:
    payload = json.loads(raw_text)
    meta = payload.get("meta", {})
    sections_data = payload.get("sections", [])
    sections = []

    for section_data in sections_data:
        section_name = normalize_sentence(section_data.get("name", "未命名板块"))
        section_intro = normalize_sentence(section_data.get("intro", section_name))
        items = []

        for item_data in section_data.get("items", []):
            items.append(
                NewsItem(
                    headline=normalize_sentence(item_data["headline"]),
                    source=normalize_sentence(item_data.get("source", "来源待补充")),
                    visual=normalize_sentence(item_data.get("visual", "focus")).lower(),
                    script=normalize_sentence(item_data["script"]),
                    takeaway=normalize_sentence(item_data.get("takeaway", "")),
                    facts=normalize_list(item_data.get("facts", [])),
                    keywords=normalize_list(item_data.get("keywords", [])),
                    watch=normalize_sentence(item_data.get("watch", "")),
                    section=section_name,
                )
            )

        sections.append(NewsSection(name=section_name, intro=section_intro, items=items))

    title = normalize_sentence(meta.get("title", "今日 AI 新闻简报"))
    subtitle = normalize_sentence(meta.get("subtitle", "AI 辅助生成 · 公开信息整理"))
    date_text = normalize_sentence(meta.get("date", ""))
    opening = normalize_sentence(meta.get("opening", ""))
    closing = normalize_sentence(meta.get("closing", ""))

    if not date_text:
        raise ValueError("meta.date 不能为空。")
    if not opening:
        raise ValueError("meta.opening 不能为空。")
    if not closing:
        raise ValueError("meta.closing 不能为空。")
    if not sections:
        raise ValueError("sections 不能为空。")

    return NewsScript(
        title=title,
        subtitle=subtitle,
        date=date_text,
        opening=opening,
        closing=closing,
        sections=sections,
        raw_text=raw_text,
        legacy_mode=False,
    )


def _load_legacy_script(raw_text: str) -> NewsScript:
    paragraphs = [p.strip() for p in raw_text.splitlines() if p.strip()]
    if not paragraphs:
        raise ValueError("稿件内容为空。")

    match = re.search(r"(\d{4}) 年 (\d{1,2}) 月 (\d{1,2}) 日", raw_text)
    date_text = ""
    if match:
        date_text = f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    item = NewsItem(
        headline="完整播报",
        source="手动整理",
        visual="focus",
        script=normalize_sentence(" ".join(paragraphs[1:-1] or paragraphs)),
        takeaway=normalize_sentence(paragraphs[-2] if len(paragraphs) > 2 else paragraphs[-1]),
        facts=split_sentences(" ".join(paragraphs[1:4]))[:3],
        keywords=[],
        watch="",
        section="今日播报",
    )
    return NewsScript(
        title="今日 AI 新闻简报",
        subtitle="兼容旧版纯文本稿件",
        date=date_text or "未设置日期",
        opening=normalize_sentence(paragraphs[0]),
        closing=normalize_sentence(paragraphs[-1]),
        sections=[NewsSection(name="今日播报", intro="下面进入今天的主要内容。", items=[item])],
        raw_text=raw_text,
        legacy_mode=True,
    )


def build_narration_text(script: NewsScript) -> str:
    parts = [script.opening]
    for section in script.sections:
        if section.intro:
            parts.append(section.intro)
        for item in section.items:
            parts.append(item.script)
    parts.append(script.closing)
    return "\n\n".join(part for part in parts if part.strip())


def build_subtitle_lines(script: NewsScript) -> list[str]:
    return split_sentences(build_narration_text(script))


def resolve_executable(name: str) -> str | None:
    existing = shutil.which(name)
    if existing:
        return existing

    for candidate in EXECUTABLE_CANDIDATES.get(name, []):
        if Path(candidate).exists():
            return candidate
    return None


def require_executable(name: str) -> str:
    path = resolve_executable(name)
    if not path:
        raise FileNotFoundError(f"找不到可执行文件: {name}")
    return path


def find_font() -> str:
    env_font = os.environ.get("NEWS_FONT_PATH")
    if env_font and Path(env_font).exists():
        return env_font

    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    raise FileNotFoundError("找不到中文字体，请检查 NEWS_FONT_PATH 或 macOS 字体路径。")
