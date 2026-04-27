import importlib
import platform
import shutil
from datetime import date
from pathlib import Path

from news_pipeline import SCRIPT_PATH, find_font, load_news_script, require_executable

REQUIRED_IMPORTS = [
    ("PIL", "pillow"),
]


def check_imports():
    for module_name, package_name in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module_name)
        except ImportError as exc:
            raise RuntimeError(f"缺少 Python 依赖 {package_name}。") from exc


def main():
    script = load_news_script(SCRIPT_PATH)
    check_imports()

    ffmpeg_path = require_executable("ffmpeg")
    ffprobe_path = require_executable("ffprobe")
    font_path = find_font()
    swift_available = shutil.which("swift") is not None
    edge_tts_available = True
    try:
        importlib.import_module("edge_tts")
    except ImportError:
        edge_tts_available = False
    say_available = shutil.which("say") is not None

    Path("output").mkdir(exist_ok=True)

    if not Path("input/background.jpg").exists():
        raise FileNotFoundError("缺少 input/background.jpg")

    script_date = script.date
    today = date.today().isoformat()
    if script_date != "未设置日期" and script_date != today:
        print(f"Warning: 稿件日期为 {script_date}，系统日期为 {today}。")

    print(f"Python: {platform.python_version()}")
    print(f"Script mode: {'legacy' if script.legacy_mode else 'structured'}")
    print(f"Title: {script.title}")
    print(f"Date: {script_date}")
    print(f"Sections: {len(script.sections)}")
    print(f"FFmpeg: {ffmpeg_path}")
    print(f"FFprobe: {ffprobe_path}")
    print(f"Font: {font_path}")
    print(f"Swift: {'yes' if swift_available else 'no'}")
    print(f"Edge TTS module: {'yes' if edge_tts_available else 'no'}")
    print(f"macOS say: {'yes' if say_available else 'no'}")
    print("Preflight OK")


if __name__ == "__main__":
    main()
