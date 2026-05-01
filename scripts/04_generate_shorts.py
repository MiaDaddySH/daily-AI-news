import asyncio
import os
import re
import subprocess
import wave
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

from news_pipeline import (
    NewsItem,
    NewsScript,
    NewsSection,
    find_font,
    load_news_script,
    require_executable,
    split_sentences,
)

BACKGROUND = Path("input/background.jpg")
BGM = Path("input/bgm.mp3")
OUTPUT_ROOT = Path(os.environ.get("SHORTS_OUTPUT_DIR", "output/shorts"))

WIDTH = 1080
HEIGHT = 1920
FPS = 6

INTRO_SECONDS = 0.8
OUTRO_SECONDS = 0.8

VOICE = os.environ.get("EDGE_TTS_VOICE", "zh-CN-YunjianNeural")
RATE = os.environ.get("EDGE_TTS_RATE", "-5%")
VOLUME = os.environ.get("EDGE_TTS_VOLUME", "+0%")
PITCH = os.environ.get("EDGE_TTS_PITCH", "+0Hz")
RETRIES = int(os.environ.get("EDGE_TTS_RETRIES", "3"))

PALETTES = {
    "focus": ((16, 33, 64), (65, 140, 255)),
    "policy": ((34, 44, 80), (255, 181, 71)),
    "data": ((10, 49, 63), (39, 214, 164)),
    "alert": ((66, 22, 28), (255, 104, 104)),
    "world": ((34, 54, 88), (121, 196, 255)),
    "science": ((30, 24, 69), (162, 123, 255)),
    "market": ((31, 56, 34), (138, 221, 109)),
    "recap": ((47, 31, 57), (255, 214, 102)),
    "section": ((25, 30, 49), (255, 255, 255)),
    "economy": ((24, 53, 37), (120, 221, 145)),
    "weather": ((18, 46, 74), (111, 196, 255)),
    "culture": ((82, 53, 18), (255, 206, 112)),
    "energy": ((43, 31, 14), (255, 170, 66)),
    "conflict": ((71, 24, 28), (255, 123, 123)),
    "legal": ((42, 35, 66), (176, 146, 255)),
    "transport": ((22, 45, 76), (115, 186, 255)),
    "map": ((34, 40, 60), (178, 187, 206)),
}


@dataclass
class ShortScene:
    kind: str
    visual: str
    section: str
    headline: str
    body: str
    source: str
    facts: list[str]
    weight: int


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "section"


def resolve_date_tag(script_date: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", script_date or ""):
        return script_date
    return date.today().strftime("%Y-%m-%d")


def wrap_cjk_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines = []
    current = ""
    for char in text:
        trial = f"{current}{char}"
        bbox = draw.textbbox((0, 0), trial, font=font, stroke_width=2)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    center_x: int,
    y: int,
    fill,
    stroke_fill=None,
    stroke_width: int = 0,
):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    x = int(center_x - ((bbox[2] - bbox[0]) / 2))
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_fill=stroke_fill,
        stroke_width=stroke_width,
    )


def draw_chip(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.FreeTypeFont, fill, text_fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + 36
    height = bbox[3] - bbox[1] + 16
    draw.rounded_rectangle((x, y, x + width, y + height), radius=14, fill=fill)
    draw.text((x + 18, y + 8), text, font=font, fill=text_fill)


def build_weighted_timeline(text_items: list[str], start_time: float, total_duration: float, weights: list[int] | None = None):
    if not text_items:
        return []
    if weights is None:
        weights = [max(len(item), 6) for item in text_items]

    total_weight = sum(weights)
    timeline = []
    current = start_time

    for idx, text in enumerate(text_items):
        raw_duration = total_duration * weights[idx] / total_weight
        scene_duration = max(1.0, raw_duration)
        end = min(current + scene_duration, start_time + total_duration)
        timeline.append((current, end, text))
        current = end
        if current >= start_time + total_duration:
            break

    start, _, text = timeline[-1]
    timeline[-1] = (start, start_time + total_duration, text)
    return timeline


def get_active_timeline_item(timeline, t):
    for start, end, item in timeline:
        if start <= t < end:
            return start, end, item
    return None


def get_audio_duration_seconds(audio_path: Path, ffprobe_bin: str) -> float:
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def section_narration_text(section: NewsSection) -> str:
    parts = [
        f"下面是{section.name}速览。",
        section.intro,
    ]
    for item in section.items:
        parts.append(item.script)
    parts.append(f"以上是{section.name}。")
    return "\n\n".join(part for part in parts if part.strip())


def build_section_subtitles(section: NewsSection) -> list[str]:
    return split_sentences(section_narration_text(section))


def build_scene_specs(section: NewsSection) -> list[ShortScene]:
    scenes: list[ShortScene] = [
        ShortScene(
            kind="section",
            visual="section",
            section=section.name,
            headline=section.name,
            body=section.intro,
            source="",
            facts=[],
            weight=max(len(section.intro), 20),
        )
    ]

    for item in section.items:
        scenes.append(
            ShortScene(
                kind="item",
                visual=item.visual or "focus",
                section=section.name,
                headline=item.headline,
                body=item.takeaway or item.script,
                source=item.source,
                facts=item.facts[:2],
                weight=max(len(item.script), len(item.headline) + 12, 28),
            )
        )

    scenes.append(
        ShortScene(
            kind="closing",
            visual="recap",
            section=section.name,
            headline="小结",
            body=f"{section.name}到这里。关注我，获取每日新闻短视频。",
            source="",
            facts=[],
            weight=20,
        )
    )
    return scenes


def render_background(base_image: Image.Image, palette):
    frame = base_image.resize((WIDTH, HEIGHT))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    deep_color, accent_color = palette

    overlay_draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(*deep_color, 105))
    overlay_draw.rectangle((0, int(HEIGHT * 0.58), WIDTH, HEIGHT), fill=(*deep_color, 140))
    overlay_draw.ellipse((-220, -180, 620, 460), fill=(*accent_color, 80))
    overlay_draw.ellipse((WIDTH - 640, HEIGHT - 620, WIDTH + 120, HEIGHT + 140), fill=(*accent_color, 60))

    frame = frame.convert("RGBA")
    frame.alpha_composite(overlay)
    return frame.convert("RGB")


def draw_intro(draw: ImageDraw.ImageDraw, script: NewsScript, section: NewsSection, fonts):
    title_font, body_font, meta_font, _ = fonts
    draw.rounded_rectangle((74, 320, WIDTH - 74, 1240), radius=42, fill=(9, 14, 28, 182))
    draw_chip(draw, 140, 410, "DAILY AI SHORTS", meta_font, (255, 255, 255, 34), (255, 255, 255, 255))
    draw_centered_text(draw, script.title, body_font, WIDTH // 2, 560, (232, 236, 244, 255))
    draw_centered_text(
        draw,
        section.name,
        title_font,
        WIDTH // 2,
        710,
        (255, 255, 255, 255),
        stroke_fill=(0, 0, 0, 200),
        stroke_width=2,
    )
    draw_centered_text(draw, script.date, body_font, WIDTH // 2, 890, (224, 228, 235, 255))


def draw_item_scene(draw: ImageDraw.ImageDraw, scene: ShortScene, fonts):
    title_font, body_font, meta_font, small_font = fonts
    card = (64, 210, WIDTH - 64, HEIGHT - 270)
    draw.rounded_rectangle(card, radius=42, fill=(10, 14, 29, 186))

    draw_chip(draw, 120, 286, scene.section, meta_font, (255, 255, 255, 28), (255, 255, 255, 255))
    if scene.source:
        draw_chip(draw, 120, 346, scene.source, meta_font, (255, 255, 255, 22), (238, 242, 248, 255))

    headline_size = 58
    headline_font = title_font.font_variant(size=headline_size)
    headline_lines = wrap_cjk_text(draw, scene.headline, headline_font, WIDTH - 220)
    while len(headline_lines) > 3 and headline_size > 42:
        headline_size -= 4
        headline_font = title_font.font_variant(size=headline_size)
        headline_lines = wrap_cjk_text(draw, scene.headline, headline_font, WIDTH - 220)

    y = 470
    for line in headline_lines[:3]:
        draw.text(
            (120, y),
            line,
            font=headline_font,
            fill=(255, 255, 255, 255),
            stroke_fill=(0, 0, 0, 180),
            stroke_width=2,
        )
        y += headline_size + 20

    body_lines = wrap_cjk_text(draw, scene.body, body_font, WIDTH - 220)
    y += 24
    for line in body_lines[:3]:
        draw.text((120, y), line, font=body_font, fill=(236, 240, 246, 255))
        y += 58

    if scene.facts:
        y += 16
        draw_chip(draw, 120, y, "要点", meta_font, (255, 255, 255, 28), (255, 255, 255, 255))
        y += 64
        for fact in scene.facts[:2]:
            fact_lines = wrap_cjk_text(draw, f"• {fact}", small_font, WIDTH - 220)
            for line in fact_lines[:2]:
                draw.text((120, y), line, font=small_font, fill=(229, 235, 244, 255))
                y += 44
            y += 12


def draw_closing_scene(draw: ImageDraw.ImageDraw, scene: ShortScene, fonts):
    title_font, body_font, meta_font, _ = fonts
    draw.rounded_rectangle((88, 430, WIDTH - 88, 1320), radius=42, fill=(10, 14, 29, 190))
    draw_chip(draw, 150, 520, "END", meta_font, (255, 255, 255, 32), (255, 255, 255, 255))
    draw_centered_text(draw, "感谢观看", title_font, WIDTH // 2, 650, (255, 255, 255, 255))

    lines = wrap_cjk_text(draw, scene.body, body_font, WIDTH - 260)
    y = 820
    for line in lines[:3]:
        draw_centered_text(draw, line, body_font, WIDTH // 2, y, (232, 236, 244, 255))
        y += 62


def draw_subtitle(draw: ImageDraw.ImageDraw, subtitle: str, font: ImageFont.FreeTypeFont):
    if not subtitle:
        return

    lines = wrap_cjk_text(draw, subtitle, font, WIDTH - 170)
    box_height = 72 + len(lines) * 56
    top = HEIGHT - box_height - 74
    draw.rounded_rectangle((52, top, WIDTH - 52, HEIGHT - 36), radius=26, fill=(0, 0, 0, 165))

    y = top + 22
    for line in lines[:2]:
        draw_centered_text(
            draw,
            line,
            font,
            WIDTH // 2,
            y,
            (255, 255, 255, 255),
            stroke_fill=(0, 0, 0, 220),
            stroke_width=2,
        )
        y += 56


def draw_scene(draw: ImageDraw.ImageDraw, scene: ShortScene, fonts):
    if scene.kind == "section":
        title_font, body_font, _, _ = fonts
        draw.rounded_rectangle((74, 430, WIDTH - 74, 1320), radius=42, fill=(10, 14, 29, 190))
        draw_centered_text(draw, scene.headline, title_font, WIDTH // 2, 640, (255, 255, 255, 255))
        lines = wrap_cjk_text(draw, scene.body, body_font, WIDTH - 220)
        y = 860
        for line in lines[:2]:
            draw_centered_text(draw, line, body_font, WIDTH // 2, y, (232, 236, 244, 255))
            y += 62
    elif scene.kind == "item":
        draw_item_scene(draw, scene, fonts)
    else:
        draw_closing_scene(draw, scene, fonts)


async def synthesize_to_mp3(text: str, target_mp3: Path):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate=RATE,
        volume=VOLUME,
        pitch=PITCH,
    )
    await communicate.save(str(target_mp3))


async def synthesize_with_retries(text: str, target_mp3: Path):
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            await synthesize_to_mp3(text, target_mp3)
            return
        except Exception as exc:
            last_error = exc
            if attempt == RETRIES:
                break
            await asyncio.sleep(min(2 * attempt, 6))

    message = str(last_error) if last_error else "unknown error"
    if "speech.platform.bing.com" in message or "ClientConnector" in message or "getaddrinfo" in message:
        raise RuntimeError(
            "Edge TTS 无法连接到远端语音服务，请确认当前环境允许联网。"
        ) from last_error
    raise RuntimeError(f"Edge TTS 生成失败: {message}") from last_error


def convert_mp3_to_wav(source_mp3: Path, target_wav: Path, ffmpeg_bin: str):
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", str(source_mp3), "-ar", "44100", "-ac", "2", str(target_wav)],
        check=True,
        capture_output=True,
        text=True,
    )


def pad_audio(input_wav: Path, output_wav: Path, intro_seconds: float, outro_seconds: float):
    with wave.open(str(input_wav), "rb") as src:
        params = src.getparams()
        frames = src.readframes(src.getnframes())

    nchannels, sampwidth, framerate, _, _, _ = params
    intro_frames = int(framerate * intro_seconds)
    outro_frames = int(framerate * outro_seconds)
    intro_silence = b"\x00" * intro_frames * nchannels * sampwidth
    outro_silence = b"\x00" * outro_frames * nchannels * sampwidth

    with wave.open(str(output_wav), "wb") as dst:
        dst.setparams(params)
        dst.writeframes(intro_silence)
        dst.writeframes(frames)
        dst.writeframes(outro_silence)


def render_section_frames(
    script: NewsScript,
    section: NewsSection,
    narration_audio: Path,
    padded_audio: Path,
    frames_dir: Path,
    frame_list: Path,
    ffprobe_bin: str,
):
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("frame_*.jpg"):
        old.unlink()

    font_path = find_font()
    fonts = (
        ImageFont.truetype(font_path, 78),
        ImageFont.truetype(font_path, 42),
        ImageFont.truetype(font_path, 30),
        ImageFont.truetype(font_path, 34),
    )
    subtitle_font = ImageFont.truetype(font_path, 40)

    narration_duration = get_audio_duration_seconds(narration_audio, ffprobe_bin)
    total_duration = get_audio_duration_seconds(padded_audio, ffprobe_bin)

    scenes = build_scene_specs(section)
    scene_timeline = build_weighted_timeline(
        [scene.body for scene in scenes],
        INTRO_SECONDS,
        narration_duration,
        [scene.weight for scene in scenes],
    )

    subtitle_timeline = build_weighted_timeline(
        build_section_subtitles(section),
        INTRO_SECONDS,
        narration_duration,
    )

    background = Image.open(BACKGROUND).convert("RGB")
    total_frames = int(total_duration * FPS) + 1
    frame_paths = []

    for frame_index in range(total_frames):
        t = frame_index / FPS

        if t < INTRO_SECONDS:
            frame = render_background(background, PALETTES["focus"])
            draw = ImageDraw.Draw(frame, "RGBA")
            draw_intro(draw, script, section, fonts)
        elif t >= total_duration - OUTRO_SECONDS:
            frame = render_background(background, PALETTES["recap"])
            draw = ImageDraw.Draw(frame, "RGBA")
            draw_closing_scene(
                draw,
                ShortScene(
                    kind="closing",
                    visual="recap",
                    section=section.name,
                    headline="感谢观看",
                    body=f"{section.name}到这里。关注我，获取每日新闻短视频。",
                    source="",
                    facts=[],
                    weight=20,
                ),
                fonts,
            )
        else:
            active_scene = get_active_timeline_item(scene_timeline, t)
            scene_index = scene_timeline.index(active_scene) if active_scene else 0
            scene = scenes[scene_index]
            palette = PALETTES.get(scene.visual, PALETTES["focus"])
            frame = render_background(background, palette)
            draw = ImageDraw.Draw(frame, "RGBA")
            draw_scene(draw, scene, fonts)

            active_subtitle = get_active_timeline_item(subtitle_timeline, t)
            subtitle = active_subtitle[2] if active_subtitle else ""
            draw_subtitle(draw, subtitle, subtitle_font)

        frame_path = frames_dir / f"frame_{frame_index:05d}.jpg"
        frame.save(frame_path, quality=88)
        frame_paths.append(frame_path)

    with frame_list.open("w", encoding="utf-8") as handle:
        for frame_path in frame_paths:
            handle.write(f"file '{frame_path.resolve()}'\n")
            handle.write(f"duration {1 / FPS}\n")
        handle.write(f"file '{frame_paths[-1].resolve()}'\n")


def merge_video(frame_list: Path, audio: Path, target_video: Path, ffmpeg_bin: str):
    if BGM.exists():
        command = [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(frame_list),
            "-i",
            str(audio),
            "-stream_loop",
            "-1",
            "-i",
            str(BGM),
            "-filter_complex",
            "[1:a]volume=1.0[a0];[2:a]volume=0.06[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "25",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-shortest",
            str(target_video),
        ]
    else:
        command = [
            ffmpeg_bin,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(frame_list),
            "-i",
            str(audio),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "25",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-shortest",
            str(target_video),
        ]

    subprocess.run(command, check=True, capture_output=True, text=True)


async def generate_short_for_section(script: NewsScript, section: NewsSection, index: int, ffmpeg_bin: str, ffprobe_bin: str):
    date_tag = resolve_date_tag(script.date)
    slug = slugify(section.name)
    section_dir = OUTPUT_ROOT / f"{index:02d}_{slug}"
    section_dir.mkdir(parents=True, exist_ok=True)

    narration_mp3 = section_dir / "narration.mp3"
    narration_wav = section_dir / "narration.wav"
    audio_wav = section_dir / "audio.wav"
    frames_dir = section_dir / "frames"
    frame_list = section_dir / "frames.txt"
    video_path = section_dir / f"short_{date_tag}_{index:02d}_{slug}.mp4"

    text = section_narration_text(section)
    await synthesize_with_retries(text, narration_mp3)
    convert_mp3_to_wav(narration_mp3, narration_wav, ffmpeg_bin)
    pad_audio(narration_wav, audio_wav, INTRO_SECONDS, OUTRO_SECONDS)

    render_section_frames(
        script=script,
        section=section,
        narration_audio=narration_wav,
        padded_audio=audio_wav,
        frames_dir=frames_dir,
        frame_list=frame_list,
        ffprobe_bin=ffprobe_bin,
    )
    merge_video(frame_list, audio_wav, video_path, ffmpeg_bin)

    return video_path


async def main():
    script = load_news_script()
    ffmpeg_bin = require_executable("ffmpeg")
    ffprobe_bin = require_executable("ffprobe")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    generated = []
    for idx, section in enumerate(script.sections, start=1):
        if not section.items:
            continue
        video_path = await generate_short_for_section(script, section, idx, ffmpeg_bin, ffprobe_bin)
        generated.append(video_path)
        print(f"Short generated: {video_path}")

    if not generated:
        raise RuntimeError("没有可生成短视频的 section。")

    print(f"Generated {len(generated)} short videos in {OUTPUT_ROOT}")


if __name__ == "__main__":
    asyncio.run(main())
