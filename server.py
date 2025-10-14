from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse, HTMLResponse
import subprocess, uuid, os, shlex, glob, shutil
from pathlib import Path

app = FastAPI()

# Paths – adjust to match your Colab project structure
PROJECT_ROOT = Path("/app")  # or Path(__file__).resolve().parent
DATA_ROOT    = PROJECT_ROOT / "data" / "May"
DEMO_DIR     = PROJECT_ROOT / "demo"
WORKSPACE    = PROJECT_ROOT / "model" / "trial_may"
RESULTS_DIR = f"{WORKSPACE}/results"

os.makedirs(DEMO_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


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


def ensure_assets():
    # Ensure gdown exists
    try:
        _run(["gdown", "--version"])
    except Exception:
        # Install gdown at runtime if missing (should already be in requirements)
        _run([os.sys.executable, "-m", "pip", "install", "gdown"])

    # --- DATA (May) ---
    if not os.path.isdir(DATA_ROOT):
        os.makedirs(f"{PROJECT_ROOT}/data", exist_ok=True)
        zip_path = f"{PROJECT_ROOT}/data/May.zip"
        print("[BOOT] Downloading May.zip…")
        _run(["gdown", "--fuzzy", f"https://drive.google.com/uc?id={GDRIVE_DATA_ID}", "-O", zip_path])
        print("[BOOT] Unzipping May.zip…")
        _run(["unzip", "-o", zip_path, "-d", f"{PROJECT_ROOT}/data"])
        try: os.remove(zip_path)
        except: pass

        # Normalize: find any extracted dir that looks like May and move/rename it
        if not os.path.isdir(DATA_ROOT):
            candidates = [p for p in glob.glob(f"{PROJECT_ROOT}/data/*") if os.path.isdir(p)]
            # pick folder named "May" (case-insensitive) or containing expected files
            pick = None
            for p in candidates:
                base = os.path.basename(p).lower()
                if base == "may":
                    pick = p; break
            if not pick and candidates:
                # last resort: if only one folder, use it
                pick = candidates[0]
            if pick and pick != DATA_ROOT:
                print(f"[BOOT] Renaming '{pick}' -> '{DATA_ROOT}'")
                if os.path.isdir(DATA_ROOT):
                    shutil.rmtree(DATA_ROOT)
                shutil.move(pick, DATA_ROOT)

    # --- MODEL (trial_may) ---
    if not os.path.isdir(WORKSPACE):
        os.makedirs(f"{PROJECT_ROOT}/model", exist_ok=True)
        zip_path = f"{PROJECT_ROOT}/model/trial_may.zip"
        print("[BOOT] Downloading trial_may.zip…")
        _run(["gdown", "--fuzzy", f"https://drive.google.com/uc?id={GDRIVE_MODEL_ID}", "-O", zip_path])
        print("[BOOT] Unzipping trial_may.zip…")
        _run(["unzip", "-o", zip_path, "-d", f"{PROJECT_ROOT}/model"])
        try: os.remove(zip_path)
        except: pass

        if not os.path.isdir(WORKSPACE):
            candidates = [p for p in glob.glob(f"{PROJECT_ROOT}/model/*") if os.path.isdir(p)]
            pick = None
            for p in candidates:
                base = os.path.basename(p).lower()
                if base == "trial_may":
                    pick = p; break
            if not pick and candidates:
                pick = candidates[0]
            if pick and pick != WORKSPACE:
                print(f"[BOOT] Renaming '{pick}' -> '{WORKSPACE}'")
                if os.path.isdir(WORKSPACE):
                    shutil.rmtree(WORKSPACE)
                shutil.move(pick, WORKSPACE)

    # Debug tree
    def ls(path):
        try:
            return os.listdir(path)
        except Exception as e:
            return f"<err: {e}>"
    print("[BOOT] /app contents:", ls("/app"))
    print("[BOOT] /app/data contents:", ls(f"{PROJECT_ROOT}/data"))
    print("[BOOT] /app/model contents:", ls(f"{PROJECT_ROOT}/model"))
    print("[BOOT] DATA_ROOT exists:", os.path.isdir(DATA_ROOT), DATA_ROOT)
    print("[BOOT] WORKSPACE exists:", os.path.isdir(WORKSPACE), WORKSPACE)

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
    #wav_path = os.path.join(DEMO_DIR, "input.wav")
    wav_path = str(DEMO_DIR / "input.wav")


    
    tts = gTTS(text)
    tts.save(mp3_path)
    
    audio = AudioSegment.from_mp3(mp3_path)
    audio = audio.set_frame_rate(48000).set_channels(1).set_sample_width(2)  # 48k, mono, 16-bit
    audio.export(wav_path, format="wav")

    ensure_assets()

    assert os.path.isdir(DATA_ROOT), f"Missing DATA_ROOT: {DATA_ROOT}"
    assert os.path.isdir(WORKSPACE), f"Missing WORKSPACE: {WORKSPACE}"
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

    # helpful asserts (catch missing assets early)
    assert DATA_ROOT.is_dir(), f"Missing DATA_ROOT: {DATA_ROOT}"
    assert WORKSPACE.is_dir(), f"Missing WORKSPACE: {WORKSPACE}"
    assert os.path.exists(wav_path) and os.path.getsize(wav_path) > 0, "WAV not created or empty"
    
    # ensure imports resolve in the child too
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = f"/app:{child_env.get('PYTHONPATH','')}"
    
    subprocess.run(cmd, check=True, env=child_env)

    #subprocess.run(shlex.split(cmd), check=True)

    # 3. Find newest mp4
    mp4_files = glob.glob(f"{RESULTS_DIR}/*.mp4")
    newest = max(mp4_files, key=os.path.getmtime)

    return HTMLResponse(f"""
    <html><body style='font-family:system-ui'>
      <h3>Input:</h3><p>{text}</p>
      <h3>Output video:</h3>
      <video controls width="640">
        <source src="/file?path={newest}" type="video/mp4">
      </video>
      <br><br><a href="/">Go back</a>
    </body></html>
    """)

@app.get("/file")
def serve_file(path: str):
    return JSONResponse({"error": "serve with nginx"}, status_code=404)
