import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SERIES_DIR = Path(os.environ.get("LANG_SERIES_DIR", "input/language_series"))
OUTPUT_ROOT = Path(os.environ.get("LANG_SERIES_OUTPUT_DIR", "output/language_series"))

DEFAULT_SERIES_FILES = [
    Path(os.environ.get("LANG_SERIES_EN_FILE", "input/language_series/english_lessons.json")),
    Path(os.environ.get("LANG_SERIES_DE_FILE", "input/language_series/german_lessons.json")),
]

VOICE_BY_LANG = {
    "en": os.environ.get("LANG_SERIES_VOICE_EN", "en-US-ChristopherNeural"),
    "de": os.environ.get("LANG_SERIES_VOICE_DE", "de-DE-KillianNeural"),
}

RATE_BY_LANG = {
    "en": os.environ.get("LANG_SERIES_RATE_EN", "-18%"),
    "de": os.environ.get("LANG_SERIES_RATE_DE", "-18%"),
}
DRY_RUN = os.environ.get("LANG_SERIES_DRY_RUN", "0") == "1"


@dataclass
class LessonVideoSpec:
    language: str
    series_title: str
    lesson_id: str
    headline: str
    narration: str
    display_body: str
    facts: list[str]
    keywords: list[str]
    source: str
    visual: str


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "lesson"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_list(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, list):
        return [normalize_text(str(v)) for v in values if normalize_text(str(v))]
    return [normalize_text(str(values))]


def discover_series_files() -> list[Path]:
    files = [p for p in DEFAULT_SERIES_FILES if p.exists()]
    if files:
        return files

    if not SERIES_DIR.exists():
        return []

    discovered = []
    for path in sorted(SERIES_DIR.glob("*.json")):
        if path.is_file():
            discovered.append(path)
    return discovered


def infer_language_from_path(path: Path) -> str:
    name = path.stem.lower()
    if "english" in name or name.startswith("en") or "_en" in name:
        return "en"
    if "german" in name or "deutsch" in name or name.startswith("de") or "_de" in name:
        return "de"
    return ""


def normalize_series_payload(raw_payload, path: Path) -> dict:
    if isinstance(raw_payload, dict):
        if isinstance(raw_payload.get("lessons"), list):
            payload = dict(raw_payload)
            if not payload.get("language"):
                inferred = infer_language_from_path(path)
                if inferred:
                    payload["language"] = inferred
            return payload

        for value in raw_payload.values():
            if isinstance(value, dict) and isinstance(value.get("lessons"), list):
                payload = dict(value)
                if not payload.get("language"):
                    inferred = infer_language_from_path(path)
                    if inferred:
                        payload["language"] = inferred
                return payload

    if isinstance(raw_payload, list):
        if not raw_payload:
            raise ValueError(f"{path}: top-level list is empty.")

        for entry in raw_payload:
            if isinstance(entry, dict) and isinstance(entry.get("lessons"), list):
                payload = dict(entry)
                if not payload.get("language"):
                    inferred = infer_language_from_path(path)
                    if inferred:
                        payload["language"] = inferred
                return payload

        if all(isinstance(entry, dict) for entry in raw_payload):
            inferred = infer_language_from_path(path)
            if inferred in ("en", "de"):
                return {
                    "language": inferred,
                    "meta": {
                        "title": path.stem,
                        "source": "ChatGPT",
                        "visual": "science",
                    },
                    "lessons": raw_payload,
                }

    raise ValueError(
        f"{path}: unsupported JSON shape. Expected an object with language/meta/lessons, "
        "or a list containing such an object."
    )


def parse_series(path: Path) -> tuple[dict, list[LessonVideoSpec]]:
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    payload = normalize_series_payload(raw_payload, path)

    language = (payload.get("language") or "").strip().lower()
    if language not in ("en", "de"):
        raise ValueError(f"{path}: language must be 'en' or 'de'.")

    meta = payload.get("meta", {})
    series_title = normalize_text(meta.get("title", "Language Lesson Series"))
    default_source = normalize_text(meta.get("source", "ChatGPT"))
    default_visual = normalize_text(meta.get("visual", "science")).lower()

    lessons_raw = payload.get("lessons", [])
    if not isinstance(lessons_raw, list) or not lessons_raw:
        raise ValueError(f"{path}: lessons must be a non-empty list.")

    lessons: list[LessonVideoSpec] = []
    for idx, lesson in enumerate(lessons_raw, start=1):
        lesson_id = normalize_text(lesson.get("id", f"lesson_{idx:03d}"))
        headline = normalize_text(lesson.get("headline", lesson_id))
        narration = normalize_text(lesson.get("narration", ""))
        if not narration:
            raise ValueError(f"{path}: lesson {lesson_id} missing narration.")

        display = lesson.get("display", {}) if isinstance(lesson.get("display", {}), dict) else {}
        display_body = normalize_text(display.get("body", lesson.get("display_body", headline)))
        facts = normalize_list(display.get("facts", lesson.get("facts", [])))
        keywords = normalize_list(display.get("keywords", lesson.get("keywords", [])))
        source = normalize_text(lesson.get("source", default_source))
        visual = normalize_text(lesson.get("visual", default_visual)).lower() or "science"

        lessons.append(
            LessonVideoSpec(
                language=language,
                series_title=series_title,
                lesson_id=lesson_id,
                headline=headline,
                narration=narration,
                display_body=display_body or headline,
                facts=facts[:3],
                keywords=keywords[:4],
                source=source,
                visual=visual,
            )
        )

    return payload, lessons


def build_short_script_json(spec: LessonVideoSpec) -> dict:
    today = date.today().isoformat()
    return {
        "meta": {
            "title": spec.series_title,
            "subtitle": "Bilingual learning card for Chinese learners",
            "date": today,
            "opening": spec.narration,
            "closing": spec.display_body,
        },
        "sections": [
            {
                "name": spec.headline,
                "intro": "",
                "items": [
                    {
                        "headline": spec.headline,
                        "source": spec.source,
                        "visual": spec.visual,
                        "keywords": spec.keywords,
                        "facts": spec.facts,
                        "takeaway": spec.display_body,
                        "script": spec.narration,
                    }
                ],
            }
        ],
    }


def write_temp_script(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_single_lesson(spec: LessonVideoSpec, lesson_index: int, lang_output_dir: Path):
    lesson_slug = slugify(f"{lesson_index:03d}_{spec.lesson_id}_{spec.headline}")
    lesson_dir = lang_output_dir / lesson_slug
    lesson_dir.mkdir(parents=True, exist_ok=True)

    temp_script = lesson_dir / "_lesson_script.json"
    write_temp_script(temp_script, build_short_script_json(spec))

    env = os.environ.copy()
    env["NEWS_SCRIPT_PATH"] = str(temp_script)
    env["SHORTS_OUTPUT_DIR"] = str(lesson_dir)
    env["EDGE_TTS_VOICE"] = VOICE_BY_LANG.get(spec.language, "zh-CN-YunjianNeural")
    env["EDGE_TTS_RATE"] = RATE_BY_LANG.get(spec.language, "-18%")
    env["SHORTS_ENFORCE_MAX_SECONDS"] = "0"
    env["SHORTS_SYNC_MODE"] = "1"
    env["SHORTS_DISPLAY_BODY_FIELD"] = "takeaway"

    print(f"\n--- Lesson {lesson_index} | {spec.language.upper()} | {spec.headline}")
    print(f"Script: {temp_script}")
    print(f"Output: {lesson_dir}")

    if DRY_RUN:
        print("Dry run enabled: skip rendering.")
        return

    subprocess.run([sys.executable, "scripts/04_generate_shorts.py"], check=True, env=env)


def run_series_file(path: Path):
    payload, lessons = parse_series(path)
    language = payload["language"].lower()
    series_title = normalize_text(payload.get("meta", {}).get("title", path.stem))

    lang_dir = OUTPUT_ROOT / f"{language}_{slugify(series_title)}"
    lang_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Series: {path.name} | language={language} | lessons={len(lessons)} ===")
    for idx, lesson in enumerate(lessons, start=1):
        run_single_lesson(lesson, idx, lang_dir)


def main():
    files = discover_series_files()
    if not files:
        raise RuntimeError(
            "No series json files found. Put english_lessons.json and german_lessons.json into input/language_series/."
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for path in files:
        run_series_file(path)

    print(f"\nDone. Series videos generated in: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
