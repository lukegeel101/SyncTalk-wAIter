#!/usr/bin/env python3
"""
Wrapper: text -> WAV -> call *existing* main.py to render the talking face video.

Usage:
  python run_talking_face.py \
    --text "Hello Luke, this is a test." \
    --data-root data/May \
    --workspace model/trial_may \
    --asr_model ave \
    --portrait

Or if you already have a WAV and just want to render:
  python run_talking_face.py \
    --wav ./demo/JNoutput.wav \
    --data-root data/May \
    --workspace model/trial_may \
    --asr_model ave \
    --portrait
"""
import argparse, os, subprocess, sys, uuid, shlex, glob, time
from pathlib import Path

# -----------------------------
# Configurable defaults
# -----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DEMO_DIR     = PROJECT_ROOT / "demo"
WORKSPACE    = PROJECT_ROOT / "model" / "trial_may"
RESULTS_DIR  = WORKSPACE / "results"

DEMO_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------
# TTS: gTTS + pydub (simple, free)
# -----------------------------
def text_to_wav_gtts(text: str, wav_out: Path, sr: int = 16000, channels: int = 1):
    """
    Generate WAV via gTTS (MP3) -> pydub convert to PCM s16 WAV.
    """
    try:
        from gtts import gTTS
        from pydub import AudioSegment
    except ImportError:
        print("Installing gTTS + pydub ...", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gtts", "pydub"])
        from gtts import gTTS
        from pydub import AudioSegment

    tmp_mp3 = DEMO_DIR / f"_tmp_{uuid.uuid4().hex}.mp3"
    gTTS(text=text, lang="en").save(str(tmp_mp3))

    audio = AudioSegment.from_mp3(str(tmp_mp3))
    audio = audio.set_frame_rate(sr).set_channels(channels).set_sample_width(2)  # 16-bit PCM
    audio.export(str(wav_out), format="wav")
    tmp_mp3.unlink(missing_ok=True)
    return wav_out

# -----------------------------
# Run your existing generator main.py
# -----------------------------
def run_face_generator(
    data_root: Path,
    workspace: Path,
    wav_path: Path,
    asr_model: str = "ave",
    portrait: bool = True,
    extra_flags: list[str] = None
):
    """
    Calls your original main.py like:
      python main.py data/May --workspace model/trial_may -O --test --test_train --asr_model ave --portrait --aud ./demo/xxx.wav
    """
    cmd = [
      "python", f"{PROJECT_ROOT}/main.py", DATA_ROOT,
      "--workspace", WORKSPACE,
      "-O", "--test", "--test_train",
      "--asr_model", "ave",
      "--portrait",
      "--aud", wav_path,
  ]
    if portrait:
        cmd.append("--portrait")
    if extra_flags:
        cmd.extend(extra_flags)

    print(">>> Running:", " ".join(shlex.quote(c) for c in cmd), flush=True)
    proc = subprocess.run(
      cmd,
      text=True,
      capture_output=True,
      env={**os.environ, "DISABLE_MIC": "1", "CUDA_VISIBLE_DEVICES": ""}  # disable mic + force CPU if needed
  )
    print(proc.stdout)
    if proc.returncode != 0:
      # Log everything so you can see it in DO logs
      print("=== main.py STDOUT ===\n", proc.stdout)
      print("=== main.py STDERR ===\n", proc.stderr)
      # Show a concise error in the page, with a snippet for debugging
      from fastapi.responses import PlainTextResponse
      return PlainTextResponse(
          f"main.py failed (exit {proc.returncode})\n\nSTDERR:\n{proc.stderr[-4000:]}",
          status_code=500
      )

    # Find newest mp4 in results
    vids = glob.glob(str(RESULTS_DIR / "*.mp4"))
    newest = max(vids, key=os.path.getmtime) if vids else None
    return newest

# -----------------------------
# CLI
# -----------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--text", type=str, help="Text to synthesize (if provided, creates WAV first).")
    p.add_argument("--wav",  type=str, help="Path to existing WAV (skip TTS).")
    p.add_argument("--data-root", default="data/May")
    p.add_argument("--workspace", default=str(WORKSPACE))
    p.add_argument("--asr_model", default="ave")
    p.add_argument("--no-portrait", action="store_true")
    p.add_argument("--sr", type=int, default=16000, help="WAV sample rate for TTS.")
    p.add_argument("--channels", type=int, default=1, help="WAV channels for TTS.")
    p.add_argument("--extra", nargs=argparse.REMAINDER, help="Any extra flags passed to your main.py")
    args = p.parse_args()

    if not args.text and not args.wav:
        p.error("Provide --text or --wav")

    # Make wav if needed
    if args.text:
        wav_out = DEMO_DIR / "JNoutput.wav"  # fixed output name your pipeline expects
        text_to_wav_gtts(args.text, wav_out, sr=args.sr, channels=args.channels)
        print(f"✅ Wrote WAV: {wav_out}")
    else:
        wav_out = Path(args.wav).resolve()
        if not wav_out.exists():
            sys.exit(f"WAV not found: {wav_out}")

    # Run generator
    newest_mp4 = run_face_generator(
        data_root=Path(args.data_root).resolve(),
        workspace=Path(args.workspace).resolve(),
        wav_path=wav_out,
        asr_model=args.asr_model,
        portrait=not args.no_portrait,
        extra_flags=args.extra
    )

    if newest_mp4:
        print(f"🎬 Output video: {newest_mp4}")
    else:
        print("⚠️ No MP4 found in results folder.")

if __name__ == "__main__":
    main()
