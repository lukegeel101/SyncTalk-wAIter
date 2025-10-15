from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse, HTMLResponse
import subprocess, uuid, os, shlex, glob, shutil, sys
from pathlib import Path
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# --- Paths (self-relative) ---
BASE = Path(__file__).resolve().parent         
PROJECT_ROOT = BASE
DATA_ROOT   = PROJECT_ROOT / "data" / "May"
WORKSPACE   = PROJECT_ROOT / "model" / "trial_may"
DEMO_DIR    = PROJECT_ROOT / "demo"
RESULTS_DIR = WORKSPACE / "results"

DEMO_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

print("[BOOT] PROJECT_ROOT:", PROJECT_ROOT)
print("[BOOT] DATA_ROOT:", DATA_ROOT, "exists:", DATA_ROOT.is_dir())
print("[BOOT] WORKSPACE:", WORKSPACE, "exists:", WORKSPACE.is_dir())

app.mount(
    "/results",
    StaticFiles(directory=str(RESULTS_DIR), html=False),
    name="results",
)

GDRIVE_DATA_ID  = "18Q2H612CAReFxBd9kxr-i1dD8U1AUfsV"  # May.zip
GDRIVE_MODEL_ID = "1C2639qi9jvhRygYHwPZDGs8pun3po3W7"  # trial_may.zip

def _run(cmd:list):
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        print("CMD FAILED:", " ".join(cmd))
        print("STDOUT:", proc.stdout)
        print("STDERR:", proc.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return proc.stdout

def latest_audio_mp4(results_dir: Path) -> Path:
    files = sorted(results_dir.glob("*_audio.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("No *_audio.mp4 found in results.")
    return files[0]
    
def ensure_assets():
    # Ensure gdown exists
    try:
        _run(["gdown", "--version"])
    except Exception:
        _run([sys.executable, "-m", "pip", "install", "gdown"])

    # DATA (May)
    if not DATA_ROOT.is_dir():
        (PROJECT_ROOT / "data").mkdir(parents=True, exist_ok=True)
        zip_path = PROJECT_ROOT / "data" / "May.zip"
        print("[BOOT] Downloading May.zip…")
        _run(["gdown", "--fuzzy", f"https://drive.google.com/uc?id={GDRIVE_DATA_ID}", "-O", str(zip_path)])
        print("[BOOT] Unzipping May.zip…")
        _run(["unzip", "-o", str(zip_path), "-d", str(PROJECT_ROOT / "data")])
        try: zip_path.unlink()
        except: pass
        if not DATA_ROOT.is_dir():
            # Try to normalize folder name to "May"
            candidates = [p for p in (PROJECT_ROOT / "data").glob("*") if p.is_dir()]
            pick = next((p for p in candidates if p.name.lower() == "may"), candidates[0] if candidates else None)
            if pick and pick != DATA_ROOT:
                print(f"[BOOT] Renaming '{pick}' -> '{DATA_ROOT}'")
                if DATA_ROOT.exists():
                    shutil.rmtree(DATA_ROOT)
                shutil.move(str(pick), str(DATA_ROOT))

    # MODEL (trial_may)
    if not WORKSPACE.is_dir():
        (PROJECT_ROOT / "model").mkdir(parents=True, exist_ok=True)
        zip_path = PROJECT_ROOT / "model" / "trial_may.zip"
        print("[BOOT] Downloading trial_may.zip…")
        _run(["gdown", "--fuzzy", f"https://drive.google.com/uc?id={GDRIVE_MODEL_ID}", "-O", str(zip_path)])
        print("[BOOT] Unzipping trial_may.zip…")
        _run(["unzip", "-o", str(zip_path), "-d", str(PROJECT_ROOT / "model")])
        try: zip_path.unlink()
        except: pass
        if not WORKSPACE.is_dir():
            candidates = [p for p in (PROJECT_ROOT / "model").glob("*") if p.is_dir()]
            pick = next((p for p in candidates if p.name.lower() == "trial_may"), candidates[0] if candidates else None)
            if pick and pick != WORKSPACE:
                print(f"[BOOT] Renaming '{pick}' -> '{WORKSPACE}'")
                if WORKSPACE.exists():
                    shutil.rmtree(WORKSPACE)
                shutil.move(str(pick), str(WORKSPACE))

    # Debug tree (use PROJECT_ROOT, not /app)
    def ls(p: Path):
        try:
            return os.listdir(p)
        except Exception as e:
            return f"<err: {e}>"
    print("[BOOT] PROJECT_ROOT contents:", ls(PROJECT_ROOT))
    print("[BOOT] DATA dir contents:", ls(PROJECT_ROOT / "data"))
    print("[BOOT] MODEL dir contents:", ls(PROJECT_ROOT / "model"))
    print("[BOOT] DATA_ROOT exists:", DATA_ROOT.is_dir(), DATA_ROOT)
    print("[BOOT] WORKSPACE exists:", WORKSPACE.is_dir(), WORKSPACE)

@app.get("/")
def index():
    return HTMLResponse("""
    <html><body style='font-family:system-ui'>
      <h2>Text → Talking Face Demo</h2>
      <form action="/generate" method="post">
        <textarea name="text" rows="4" cols="60" placeholder="Type something..."></textarea><br><br>
        <input type="submit" value="Generate Video">
      </form>
    </body></html>
    """)

@app.post("/generate")
def generate(text: str = Form(...)):
    # use gTTS
    from gtts import gTTS
    from pydub import AudioSegment
    
    # 1. Generate WAV from text
    mp3_path = os.path.join(DEMO_DIR, "input.mp3")
    wav_path = str(DEMO_DIR / "input.wav")
    
    tts = gTTS(text)
    tts.save(mp3_path)
    
    audio = AudioSegment.from_mp3(mp3_path)
    audio = audio.set_frame_rate(48000).set_channels(1).set_sample_width(2)  # 48k, mono, 16-bit
    audio.export(wav_path, format="wav")

    ensure_assets()

    assert DATA_ROOT.is_dir(), f"Missing DATA_ROOT: {DATA_ROOT}"
    assert WORKSPACE.is_dir(), f"Missing WORKSPACE: {WORKSPACE}"
    assert os.path.exists(wav_path) and os.path.getsize(wav_path) > 0, "WAV not created or empty"

    # 2. Run your generator
    cmd = [
        sys.executable,                          # <-- was "python"
        str(PROJECT_ROOT / "main.py"),
        str(DATA_ROOT),
        "--workspace", str(WORKSPACE),
        "-O", "--test", "--test_train",
        "--asr_model", "ave",
        "--portrait",
        "--aud", wav_path,
    ]    
    
    # ensure imports resolve in the child too
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = f"{PROJECT_ROOT}:{child_env.get('PYTHONPATH','')}"
    
    subprocess.run(cmd, check=True, env=child_env)

    #subprocess.run(shlex.split(cmd), check=True)

    out_path = latest_audio_mp4(RESULTS_DIR)
    rel_url = f"/results/{out_path.name}"
    return HTMLResponse(f"""
    <html>
      <body style='font-family:system-ui'>
        <h3>Input:</h3><p>{text}</p>

        <h3>Output video:</h3>
        <video id="vid" controls width="640">
          <source src="{rel_url}" type="video/mp4">
          Your browser does not support MP4 playback.
        </video>

        <p><a id="dl" href="{rel_url}" download>Download video</a></p>

        <script>
          // Auto-start download once the page renders
          (function () {{
            const a = document.getElementById('dl');
            if (a) a.click();
          }})();
        </script>

        <br><br><a href="/">Go back</a>
      </body>
    </html>
    """)

@app.get("/file")
def serve_file(path: str):
    return JSONResponse({"error": "serve with nginx"}, status_code=404)
