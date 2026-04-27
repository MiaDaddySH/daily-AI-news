from pathlib import Path
import wave

INPUT_WAV = Path("output/narration.wav")
OUTPUT_WAV = Path("output/audio.wav")

INTRO_SECONDS = 3
OUTRO_SECONDS = 5


def make_silence(params, seconds):
    nchannels, sampwidth, framerate, _, _, _ = params
    frame_count = int(framerate * seconds)
    return b"\x00" * frame_count * nchannels * sampwidth


def main():
    with wave.open(str(INPUT_WAV), "rb") as src:
        params = src.getparams()
        frames = src.readframes(src.getnframes())

    intro_silence = make_silence(params, INTRO_SECONDS)
    outro_silence = make_silence(params, OUTRO_SECONDS)

    with wave.open(str(OUTPUT_WAV), "wb") as dst:
        dst.setparams(params)
        dst.writeframes(intro_silence)
        dst.writeframes(frames)
        dst.writeframes(outro_silence)

    print(f"Padded audio generated: {OUTPUT_WAV}")


if __name__ == "__main__":
    main()
