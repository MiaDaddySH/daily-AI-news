import subprocess
from dataclasses import dataclass
from pathlib import Path

from news_pipeline import (
    build_subtitle_lines,
    find_font,
    load_news_script,
    require_executable,
)
from PIL import Image, ImageDraw, ImageFont

BACKGROUND = Path("input/background.jpg")
NARRATION_AUDIO = Path("output/narration.wav")
PADDED_AUDIO = Path("output/audio.wav")
FRAMES_DIR = Path("output/frames")
FRAME_LIST = Path("output/frames.txt")

WIDTH = 1920
HEIGHT = 1080
FPS = 4

INTRO_SECONDS = 3
OUTRO_SECONDS = 5

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
}


@dataclass
class SceneSpec:
    kind: str
    visual: str
    section: str
    headline: str
    source: str
    body: str
    deck: str
    callout: str
    facts: list[str]
    keywords: list[str]
    weight: int


def get_audio_duration_seconds(audio_path: Path) -> float:
    ffprobe_bin = require_executable("ffprobe")
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


CARD_LEFT = 120
CARD_TOP = 140
CARD_RIGHT = 1800
CARD_BOTTOM = 860
CARD_PANEL = (CARD_LEFT, CARD_TOP, CARD_RIGHT, CARD_BOTTOM)
CARD_RADIUS = 38
SOURCE_CHIP = (170, 190)
VISUAL_CHIP = (390, 190)
LEFT_TEXT_X = 170
RIGHT_RAIL_X = 1230
RIGHT_RAIL_RIGHT = 1710


def draw_card_shell(draw):
    draw.rounded_rectangle(CARD_PANEL, radius=CARD_RADIUS, fill=(10, 14, 29, 182))


def draw_source_visual_chips(draw, source, visual, meta_font):
    draw_chip(
        draw,
        SOURCE_CHIP[0],
        SOURCE_CHIP[1],
        source,
        meta_font,
        (255, 255, 255, 35),
        (255, 255, 255, 255),
    )
    draw_chip(
        draw,
        VISUAL_CHIP[0],
        VISUAL_CHIP[1],
        visual.upper(),
        meta_font,
        (255, 255, 255, 25),
        (232, 236, 244, 255),
    )


def draw_keyword_stack(draw, keywords, body_font, meta_font):
    if not keywords:
        return

    # 标签
    draw_chip(
        draw,
        RIGHT_RAIL_X,
        238,
        "关键词",
        meta_font,
        (255, 255, 255, 35),
        (255, 255, 255, 255),
    )

    # 关键词列表
    start_y = 300
    for index, keyword in enumerate(keywords[:4]):
        y = start_y + index * 92
        draw.rounded_rectangle(
            (RIGHT_RAIL_X, y, RIGHT_RAIL_RIGHT, y + 62),
            radius=24,
            fill=(255, 255, 255, 28),
        )
        draw.text(
            (RIGHT_RAIL_X + 30, y + 14),
            keyword,
            font=body_font,
            fill=(238, 240, 244, 255),
        )


def draw_fact_stack_vertical(draw, facts, small_font, start_y):
    if not facts:
        return

    box_left = LEFT_TEXT_X
    box_right = CARD_RIGHT - 90
    max_width = box_right - box_left - 40

    line_spacing = 38
    inner_top = 16
    inner_bottom = 16
    item_gap = 18

    current_y = start_y

    for fact in facts[:3]:
        lines = wrap_cjk_text(draw, fact, small_font, max_width)[:2]
        line_count = max(1, len(lines))

        box_height = inner_top + inner_bottom + line_count * line_spacing

        draw.rounded_rectangle(
            (box_left, current_y, box_right, current_y + box_height),
            radius=20,
            fill=(255, 255, 255, 20),
        )

        line_y = current_y + inner_top
        for line in lines:
            draw.text(
                (box_left + 20, line_y),
                line,
                font=small_font,
                fill=(232, 238, 245, 255),
            )
            line_y += line_spacing

        current_y += box_height + item_gap


def build_scene_specs(script):
    scenes = []

    for section in script.sections:
        scenes.append(
            SceneSpec(
                kind="section",
                visual="section",
                section=section.name,
                headline=section.name,
                source="",
                body=section.intro,
                deck=script.subtitle,
                callout=section.intro,
                facts=[],
                keywords=[],
                weight=max(len(section.intro), 18),
            )
        )

        for item in section.items:
            primary_weight = max(
                int(len(item.script) * 0.42), len(item.headline) + 16, 20
            )
            impact_weight = max(
                int(len(item.script) * 0.58), len(item.takeaway) + 20, 26
            )
            facts = item.facts[:3]

            scenes.append(
                SceneSpec(
                    kind="headline",
                    visual=item.visual or "focus",
                    section=section.name,
                    headline=item.headline,
                    source=item.source,
                    body=item.script,
                    deck="",
                    callout="",
                    facts=facts,
                    keywords=item.keywords[:4],
                    weight=primary_weight,
                )
            )

            scenes.append(
                SceneSpec(
                    kind="impact",
                    visual=item.visual or "focus",
                    section=section.name,
                    headline=item.headline,
                    source=item.source,
                    body=item.takeaway or item.script,
                    deck="",
                    callout="",
                    facts=facts,
                    keywords=item.keywords[:4],
                    weight=impact_weight,
                )
            )

    scenes.append(
        SceneSpec(
            kind="closing",
            visual="recap",
            section="收尾",
            headline="今日内容回顾",
            source="",
            body=script.closing,
            deck=script.subtitle,
            callout=script.closing,
            facts=[],
            keywords=[],
            weight=max(len(script.closing), 20),
        )
    )
    return scenes


def build_weighted_timeline(text_items, start_time, total_duration, weights=None):
    if weights is None:
        weights = [max(len(item), 6) for item in text_items]
    total_weight = sum(weights)
    timeline = []
    current = start_time

    for idx, text in enumerate(text_items):
        raw_duration = total_duration * weights[idx] / total_weight
        scene_duration = max(1.2, raw_duration)
        end = min(current + scene_duration, start_time + total_duration)
        timeline.append((current, end, text))
        current = end
        if current >= start_time + total_duration:
            break

    if timeline:
        start, _, text = timeline[-1]
        timeline[-1] = (start, start_time + total_duration, text)
    return timeline


def get_active_timeline_item(timeline, t):
    for start, end, item in timeline:
        if start <= t < end:
            return start, end, item
    return None


def wrap_cjk_text(draw, text, font, max_width):
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
    draw, text, font, center_x, y, fill, stroke_fill=None, stroke_width=0
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


def draw_chip(draw, x, y, text, font, fill, text_fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + 44
    height = bbox[3] - bbox[1] + 20
    draw.rounded_rectangle((x, y, x + width, y + height), radius=18, fill=fill)
    draw.text((x + 22, y + 10), text, font=font, fill=text_fill)


def render_background(base_image, scene_index, progress, palette):
    frame = base_image.resize((WIDTH, HEIGHT))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    deep_color, accent_color = palette

    overlay_draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(*deep_color, 80))
    overlay_draw.rectangle((0, HEIGHT * 0.55, WIDTH, HEIGHT), fill=(*deep_color, 115))
    overlay_draw.ellipse(
        (-220, -180, 720, 540),
        fill=(*accent_color, 60),
    )
    overlay_draw.ellipse(
        (WIDTH - 760, HEIGHT - 540, WIDTH + 140, HEIGHT + 160),
        fill=(*accent_color, 30),
    )

    frame = frame.convert("RGBA")
    frame.alpha_composite(overlay)
    return frame.convert("RGB")


def draw_section_scene(draw, scene, fonts):
    title_font, body_font, meta_font, _ = fonts
    panel = (210, 220, 1710, 820)
    draw.rounded_rectangle(panel, radius=40, fill=(9, 14, 28, 175))
    draw_chip(
        draw, 300, 300, "SECTION", meta_font, (255, 255, 255, 38), (255, 255, 255, 255)
    )
    draw_centered_text(
        draw, scene.headline, title_font, WIDTH / 2, 390, (255, 255, 255, 255)
    )

    lines = wrap_cjk_text(draw, scene.body, body_font, 1120)
    y = 535
    for line in lines[:2]:
        draw_centered_text(draw, line, body_font, WIDTH / 2, y, (232, 236, 244, 255))
        y += 66


def draw_headline_scene(draw, scene, fonts):
    title_font, body_font, meta_font, small_font = fonts
    draw_card_shell(draw)
    draw_source_visual_chips(draw, scene.source, scene.visual, meta_font)

    headline_font = title_font.font_variant(size=68)
    headline_lines = wrap_cjk_text(draw, scene.headline, headline_font, 990)
    y = 290
    for line in headline_lines[:3]:
        draw.text(
            (LEFT_TEXT_X, y),
            line,
            font=headline_font,
            fill=(255, 255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 180),
        )
        y += 88

    draw_keyword_stack(draw, scene.keywords, body_font, meta_font)


def draw_impact_scene(draw, scene, fonts):
    title_font, body_font, meta_font, small_font = fonts
    draw_card_shell(draw)
    draw_source_visual_chips(draw, scene.source, scene.visual, meta_font)

    # 上半部分：takeaway（主结论）
    impact_size = 64
    if len(scene.body) > 34:
        impact_size = 58
    if len(scene.body) > 52:
        impact_size = 52
    if len(scene.body) > 68:
        impact_size = 46

    impact_font = title_font.font_variant(size=impact_size)
    max_text_width = CARD_RIGHT - CARD_LEFT - 120
    body_lines = wrap_cjk_text(draw, scene.body, impact_font, max_text_width)

    while len(body_lines) > 3 and impact_size > 36:
        impact_size -= 4
        impact_font = title_font.font_variant(size=impact_size)
        body_lines = wrap_cjk_text(draw, scene.body, impact_font, max_text_width)

    y = 290
    for line in body_lines[:3]:
        draw.text(
            (LEFT_TEXT_X, y),
            line,
            font=impact_font,
            fill=(255, 255, 255, 255),
            stroke_fill=(0, 0, 0, 180),
            stroke_width=2,
        )
        y += max(62, impact_size + 10)

    # 中间留一点呼吸空间
    facts_start_y = y + 30

    # 下半部分：facts
    if scene.facts:
        draw_chip(
            draw,
            LEFT_TEXT_X,
            facts_start_y,
            "要点",
            meta_font,
            (255, 255, 255, 30),
            (255, 255, 255, 255),
        )
        draw_fact_stack_vertical(draw, scene.facts, small_font, facts_start_y + 56)


def draw_closing_scene(draw, scene, fonts):
    title_font, body_font, meta_font, _ = fonts
    draw.rounded_rectangle((240, 240, 1680, 840), radius=42, fill=(10, 14, 29, 188))
    draw_chip(
        draw, 320, 310, "WRAP-UP", meta_font, (255, 255, 255, 34), (255, 255, 255, 255)
    )
    draw_centered_text(
        draw, scene.headline, title_font, WIDTH / 2, 395, (255, 255, 255, 255)
    )

    body_lines = wrap_cjk_text(draw, scene.body, body_font, 1180)
    y = 535
    for line in body_lines[:4]:
        draw_centered_text(draw, line, body_font, WIDTH / 2, y, (230, 236, 244, 255))
        y += 66


def draw_intro(draw, script, fonts):
    title_font, body_font, _, _ = fonts
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(0, 0, 0, 80))
    draw_centered_text(
        draw,
        script.title,
        title_font,
        WIDTH / 2,
        390,
        (255, 255, 255, 255),
        stroke_fill=(0, 0, 0, 255),
        stroke_width=2,
    )
    draw_centered_text(
        draw, script.date, body_font, WIDTH / 2, 500, (235, 235, 235, 255)
    )
    draw_centered_text(
        draw, script.subtitle, body_font, WIDTH / 2, 585, (225, 228, 235, 255)
    )


def draw_outro(draw, fonts):
    title_font, body_font, _, _ = fonts
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(0, 0, 0, 95))
    draw_centered_text(
        draw,
        "感谢收看",
        title_font,
        WIDTH / 2,
        390,
        (255, 255, 255, 255),
        stroke_fill=(0, 0, 0, 255),
        stroke_width=2,
    )
    draw_centered_text(
        draw,
        "以上内容由 AI 辅助生成，基于公开信息整理，仅供参考。",
        body_font,
        WIDTH / 2,
        520,
        (235, 235, 235, 255),
    )
    draw_centered_text(draw, "明天见", body_font, WIDTH / 2, 610, (220, 220, 220, 255))


def draw_subtitle(draw, subtitle, font):
    if not subtitle:
        return

    lines = wrap_cjk_text(draw, subtitle, font, 1380)
    box_height = 82 + len(lines) * 60
    top = HEIGHT - box_height - 72
    draw.rounded_rectangle(
        (190, top, 1730, HEIGHT - 42), radius=28, fill=(0, 0, 0, 150)
    )

    y = top + 26
    for line in lines[:2]:
        draw_centered_text(
            draw,
            line,
            font,
            WIDTH / 2,
            y,
            (255, 255, 255, 255),
            stroke_fill=(0, 0, 0, 255),
            stroke_width=2,
        )
        y += 60


def draw_scene(draw, scene, fonts):
    if scene.kind == "section":
        draw_section_scene(draw, scene, fonts)
    elif scene.kind == "headline":
        draw_headline_scene(draw, scene, fonts)
    elif scene.kind == "impact":
        draw_impact_scene(draw, scene, fonts)
    else:
        draw_closing_scene(draw, scene, fonts)


def main():
    script = load_news_script()
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    for old in FRAMES_DIR.glob("frame_*.jpg"):
        old.unlink()

    font_path = find_font()
    fonts = (
        ImageFont.truetype(font_path, 72),
        ImageFont.truetype(font_path, 40),
        ImageFont.truetype(font_path, 28),
        ImageFont.truetype(font_path, 34),
    )

    subtitle_font = ImageFont.truetype(font_path, 44)

    narration_duration = get_audio_duration_seconds(NARRATION_AUDIO)
    total_duration = get_audio_duration_seconds(PADDED_AUDIO)

    subtitles = build_subtitle_lines(script)
    subtitle_timeline = build_weighted_timeline(
        subtitles, INTRO_SECONDS, narration_duration
    )

    scenes = build_scene_specs(script)
    scene_descriptions = [scene.body for scene in scenes]
    scene_weights = [scene.weight for scene in scenes]
    scene_timeline = build_weighted_timeline(
        scene_descriptions, INTRO_SECONDS, narration_duration, scene_weights
    )

    background = Image.open(BACKGROUND).convert("RGB")
    total_frames = int(total_duration * FPS) + 1
    frame_paths = []

    for frame_index in range(total_frames):
        t = frame_index / FPS

        if t < INTRO_SECONDS:
            frame = render_background(
                background, 0, t / max(INTRO_SECONDS, 1), PALETTES["focus"]
            )
            draw = ImageDraw.Draw(frame, "RGBA")
            draw_intro(draw, script, fonts)
        elif t >= total_duration - OUTRO_SECONDS:
            frame = render_background(background, len(scenes), 1.0, PALETTES["recap"])
            draw = ImageDraw.Draw(frame, "RGBA")
            draw_outro(draw, fonts)
        else:
            active_scene = get_active_timeline_item(scene_timeline, t)
            scene_index = scene_timeline.index(active_scene) if active_scene else 0
            progress = 0.0
            if active_scene and active_scene[1] > active_scene[0]:
                progress = max(
                    0.0,
                    min(
                        (t - active_scene[0]) / (active_scene[1] - active_scene[0]), 1.0
                    ),
                )
            scene = scenes[scene_index]
            palette = PALETTES.get(scene.visual, PALETTES["focus"])
            frame = render_background(background, scene_index + 1, progress, palette)
            draw = ImageDraw.Draw(frame, "RGBA")
            draw_scene(draw, scene, fonts)

            active_subtitle = get_active_timeline_item(subtitle_timeline, t)
            subtitle = active_subtitle[2] if active_subtitle else ""
            draw_subtitle(draw, subtitle, subtitle_font)

        frame_path = FRAMES_DIR / f"frame_{frame_index:05d}.jpg"
        frame.save(frame_path, quality=86)
        frame_paths.append(frame_path)

    with FRAME_LIST.open("w", encoding="utf-8") as handle:
        for frame_path in frame_paths:
            handle.write(f"file '{frame_path.resolve()}'\n")
            handle.write(f"duration {1 / FPS}\n")
        handle.write(f"file '{frame_paths[-1].resolve()}'\n")

    print(f"Frames generated: {len(frame_paths)}")
    print(f"Frame list: {FRAME_LIST}")


if __name__ == "__main__":
    main()
