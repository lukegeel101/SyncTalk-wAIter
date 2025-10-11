import subprocess, glob, time, os
from IPython.display import HTML, display

def render_talking_face_from_text(text: str,
                                  wav_out: str = None,
                                  project_root: str = PROJECT_ROOT):
    """
    1) Synthesize text -> WAV at ./demo/JNoutput.wav (or custom path)
    2) Run your main.py with that WAV
    3) Return the newest MP4 in results and display it inline
    """
    if wav_out is None:
        wav_out = f"{DEMO_DIR}/JNoutput.wav"

    # 1) Text -> WAV
    text_to_wav(text, wav_out, target_sr=16000, channels=1)
    print(f"✅ Wrote WAV: {wav_out}")

    # 2) Run your generator
    cmd = [
        "python", f"{project_root}/main.py", "data/May",
        "--workspace", f"{project_root}/model/trial_may",
        "-O", "--test", "--test_train",
        "--asr_model", "ave",
        "--portrait",
        "--aud", wav_out
    ]
    print("🚀 Running:", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        raise RuntimeError("Generation failed.")

    # 3) Find newest MP4 in results
    pattern = os.path.join(RESULTS_DIR, "*.mp4")
    vids = glob.glob(pattern)
    if not vids:
        raise FileNotFoundError(f"No MP4 found in {RESULTS_DIR}")
    newest = max(vids, key=os.path.getmtime)
    print("🎬 Newest video:", newest)

    # 4) Show inline
    rel = newest if newest.startswith("/content") else newest
    display(HTML(f"""
    <video controls width="640">
      <source src="{rel}" type="video/mp4">
    </video>
    """))
    return newest

print("render_talking_face_from_text ready.")
