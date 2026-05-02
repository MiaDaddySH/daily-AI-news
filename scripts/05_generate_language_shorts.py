import os
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(os.environ.get("LANG_SCRIPT_DIR", "input/language_scripts"))
OUTPUT_ROOT = Path(os.environ.get("LANG_SHORTS_OUTPUT_DIR", "output/language_shorts"))
SUPPORTED_EXTS = {".txt", ".md", ".json"}

VOICE_DEFAULT = os.environ.get("LANG_SHORTS_VOICE_DEFAULT", "zh-CN-YunjianNeural")
VOICE_MAP = {
    "en": os.environ.get("LANG_SHORTS_VOICE_EN", "en-US-ChristopherNeural"),
    "de": os.environ.get("LANG_SHORTS_VOICE_DE", "de-DE-KillianNeural"),
}


def detect_language_key(path: Path) -> str:
    name = path.stem.lower()

    if any(token in name for token in ("english", "eng", "en_", "_en", "英语", "yingyu")):
        return "en"
    if any(token in name for token in ("german", "deutsch", "de_", "_de", "德语", "deyu")):
        return "de"

    # Prefix style: en-topic.txt, de-topic.txt
    if name.startswith("en-") or name.startswith("en_"):
        return "en"
    if name.startswith("de-") or name.startswith("de_"):
        return "de"

    return "default"


def resolve_voice(language_key: str) -> str:
    return VOICE_MAP.get(language_key, VOICE_DEFAULT)


def discover_script_files() -> list[Path]:
    if not SCRIPT_DIR.exists():
        return []

    files = []
    for file_path in sorted(SCRIPT_DIR.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        files.append(file_path)
    return files


def normalize_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def build_structured_script_from_plain_text(script_path: Path, language_key: str) -> dict:
    raw = script_path.read_text(encoding="utf-8")
    lines = normalize_lines(raw)
    if not lines:
        raise RuntimeError(f"Script is empty: {script_path}")

    title = lines[0]
    body_lines = lines[1:] if len(lines) > 1 else lines
    body_text = " ".join(body_lines).strip()
    opening = body_lines[0] if body_lines else title
    closing = body_lines[-1] if len(body_lines) > 1 else body_text
    section_name = title
    headline = title

    if language_key == "en":
        subtitle = "AI-generated language lesson"
        intro = "Let's start today's English point."
    elif language_key == "de":
        subtitle = "KI-gestuetzte Sprachlektion"
        intro = "Starten wir mit dem heutigen Deutschpunkt."
    else:
        subtitle = "AI 辅助生成的语言知识短视频"
        intro = "下面开始今天的语言知识点。"

    facts = body_lines[:2] if body_lines else [body_text]
    keywords = [section_name, "language", "daily"]

    return {
        "meta": {
            "title": title,
            "subtitle": subtitle,
            "date": date.today().isoformat(),
            "opening": opening,
            "closing": closing,
        },
        "sections": [
            {
                "name": section_name,
                "intro": intro,
                "items": [
                    {
                        "headline": headline,
                        "source": "ChatGPT",
                        "visual": "science",
                        "keywords": keywords,
                        "facts": facts,
                        "takeaway": closing,
                        "script": body_text or title,
                    }
                ],
            }
        ],
    }


def prepare_script_path(script_path: Path, output_dir: Path, language_key: str) -> Path:
    if script_path.suffix.lower() == ".json":
        return script_path

    structured = build_structured_script_from_plain_text(script_path, language_key)
    prepared_path = output_dir / "_prepared_script.json"
    prepared_path.write_text(
        json.dumps(structured, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return prepared_path


def run_single_script(script_path: Path):
    language_key = detect_language_key(script_path)
    voice = resolve_voice(language_key)

    output_dir = OUTPUT_ROOT / script_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_script_path = prepare_script_path(script_path, output_dir, language_key)

    env = os.environ.copy()
    env["NEWS_SCRIPT_PATH"] = str(prepared_script_path)
    env["SHORTS_OUTPUT_DIR"] = str(output_dir)
    env["EDGE_TTS_VOICE"] = voice
    env.setdefault("SHORTS_MAX_SECONDS", "59")

    print(f"\\n=== Processing: {script_path.name} ===")
    print(f"Language: {language_key}")
    print(f"Voice: {voice}")
    print(f"Script: {prepared_script_path}")
    print(f"Output dir: {output_dir}")

    subprocess.run(
        [sys.executable, "scripts/04_generate_shorts.py"],
        env=env,
        check=True,
    )


def main():
    script_files = discover_script_files()
    if not script_files:
        raise RuntimeError(
            f"No script files found in {SCRIPT_DIR}. "
            "Please put your English/German scripts into this directory."
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    for script_path in script_files:
        run_single_script(script_path)

    print(f"\\nDone. Language shorts are in: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
