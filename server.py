from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
import subprocess, uuid, os, shlex, glob, shutil, sys
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import time
import uvicorn
import tempfile
import threading
import requests
from fastapi import Body

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Paths (self-relative) ---
BASE = Path(__file__).resolve().parent         
PROJECT_ROOT = BASE
DATA_ROOT   = PROJECT_ROOT / "data" / "May"
WORKSPACE   = PROJECT_ROOT / "model" / "trial_may"
DEMO_DIR    = PROJECT_ROOT / "demo"
RESULTS_DIR = WORKSPACE / "results"

DEMO_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # or gpt-4o, gpt-4.1, etc.

print("[BOOT] PROJECT_ROOT:", PROJECT_ROOT)
print("[BOOT] DATA_ROOT:", DATA_ROOT, "exists:", DATA_ROOT.is_dir())
print("[BOOT] WORKSPACE:", WORKSPACE, "exists:", WORKSPACE.is_dir())

# Mount directories for serving files
if os.path.exists("demo"):
    app.mount("/demo", StaticFiles(directory="demo"), name="demo")
if RESULTS_DIR.exists():
    app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")

# Create results directory if it doesn't exist
os.makedirs("results", exist_ok=True)
os.makedirs("temp_uploads", exist_ok=True)

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

# Store active tasks
active_tasks = {}

def generate_video_background(task_id, audio_path):
    """Background task for video generation"""
    try:
        # Update progress
        active_tasks[task_id]["progress"] = 10
        active_tasks[task_id]["message"] = "Processing audio..."
        time.sleep(1)  # Give UI time to update
        
        # Ensure assets are ready
        ensure_assets()
        
        active_tasks[task_id]["progress"] = 30
        active_tasks[task_id]["message"] = "Generating facial expressions..."
        
        # Run SyncTalk generation
        cmd = [
            sys.executable, str(PROJECT_ROOT / "main.py"),
            str(DATA_ROOT),
            "--workspace", str(WORKSPACE),
            "-O", "--test", "--test_train",
            "--asr_model", "ave",
            "--portrait",
            "--aud", audio_path
        ]
        
        # Ensure imports resolve
        child_env = os.environ.copy()
        child_env["PYTHONPATH"] = f"{PROJECT_ROOT}:{child_env.get('PYTHONPATH','')}"
        
        result = subprocess.run(cmd, capture_output=True, text=True, env=child_env)
        
        active_tasks[task_id]["progress"] = 80
        active_tasks[task_id]["message"] = "Finalizing video..."
        
        if result.returncode != 0:
            raise Exception(f"Generation failed: {result.stderr}")
        
        # Find the generated video
        video_files = list(RESULTS_DIR.glob("*_audio.mp4"))
        video_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        if video_files:
            # The video is already in RESULTS_DIR, just update the URL
            active_tasks[task_id]["status"] = "completed"
            active_tasks[task_id]["progress"] = 100
            active_tasks[task_id]["message"] = "Video generated successfully"
            active_tasks[task_id]["video_url"] = f"/results/{video_files[0].name}"
        else:
            raise Exception("No output video found")
            
    except Exception as e:
        active_tasks[task_id]["status"] = "error"
        active_tasks[task_id]["message"] = str(e)
    finally:
        # Clean up temp file
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except:
                pass

def call_chatgpt(user_prompt: str) -> str:
    """Call OpenAI Chat Completions API and return the assistant message text."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a concise, helpful assistant."},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }
    r = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI API error {r.status_code}: {r.text}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def text_to_wav_gtts(text: str, out_wav_path: str):
    """Use gTTS -> mp3 -> wav (48k mono 16-bit) via pydub."""
    from gtts import gTTS
    from pydub import AudioSegment

    tmp_mp3 = str(Path(out_wav_path).with_suffix(".mp3"))
    tts = gTTS(text)
    tts.save(tmp_mp3)

    audio = AudioSegment.from_mp3(tmp_mp3)
    audio = audio.set_frame_rate(48000).set_channels(1).set_sample_width(2)
    audio.export(out_wav_path, format="wav")
    try:
        os.remove(tmp_mp3)
    except:
        pass

def generate_text_video_background(task_id: str, prompt_text: str):
    """End-to-end: ChatGPT → TTS(WAV) → SyncTalk video (async)."""
    temp_wav = f"temp_uploads/{task_id}_from_text.wav"
    try:
        active_tasks[task_id]["status"] = "processing"
        active_tasks[task_id]["progress"] = 5
        active_tasks[task_id]["message"] = "Contacting ChatGPT..."
        time.sleep(0.5)

        # 1) Get response text from ChatGPT
        response_text = call_chatgpt(prompt_text)

        active_tasks[task_id]["progress"] = 20
        active_tasks[task_id]["message"] = "Generating speech audio..."
        # 2) Convert to WAV with gTTS
        text_to_wav_gtts(response_text, temp_wav)
        if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) == 0:
            raise RuntimeError("TTS failed to create WAV.")

        active_tasks[task_id]["progress"] = 35
        active_tasks[task_id]["message"] = "Preparing assets..."
        ensure_assets()

        # 3) Run SyncTalk
        active_tasks[task_id]["progress"] = 60
        active_tasks[task_id]["message"] = "Rendering talking head video..."

        cmd = [
            sys.executable, str(PROJECT_ROOT / "main.py"),
            str(DATA_ROOT),
            "--workspace", str(WORKSPACE),
            "-O", "--test", "--test_train",
            "--asr_model", "ave",
            "--portrait",
            "--aud", temp_wav,
        ]
        child_env = os.environ.copy()
        child_env["PYTHONPATH"] = f"{PROJECT_ROOT}:{child_env.get('PYTHONPATH','')}"
        result = subprocess.run(cmd, capture_output=True, text=True, env=child_env)

        active_tasks[task_id]["progress"] = 85
        active_tasks[task_id]["message"] = "Finalizing video..."

        if result.returncode != 0:
            raise RuntimeError(f"Generation failed: {result.stderr}")

        # 4) Locate output and publish URL
        video_files = list(RESULTS_DIR.glob("*_audio.mp4"))
        video_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        if not video_files:
            raise RuntimeError("No output video found")

        active_tasks[task_id]["status"] = "completed"
        active_tasks[task_id]["progress"] = 100
        active_tasks[task_id]["message"] = "Done"
        active_tasks[task_id]["video_url"] = f"/results/{video_files[0].name}"

        # Optional: also store the generated script if you want to show it later
        active_tasks[task_id]["generated_text"] = response_text

    except Exception as e:
        active_tasks[task_id]["status"] = "error"
        active_tasks[task_id]["message"] = str(e)
    finally:
        try:
            if os.path.exists(temp_wav):
                os.remove(temp_wav)
        except:
            pass

@app.get("/")
async def root():
    """Home page with options"""
    return HTMLResponse("""
    <html>
        <head>
            <title>SyncTalk Video Generator</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                }
                .container {
                    background: white;
                    border-radius: 10px;
                    padding: 30px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                }
                h1 {
                    color: #333;
                    text-align: center;
                }
                .button-group {
                    display: flex;
                    gap: 20px;
                    justify-content: center;
                    margin-top: 30px;
                }
                .btn {
                    padding: 15px 30px;
                    font-size: 18px;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    text-decoration: none;
                    display: inline-block;
                    transition: transform 0.2s, box-shadow 0.2s;
                    text-align: center;
                }
                .btn-primary {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .btn-secondary {
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    color: white;
                }
                .btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(0,0,0,0.3);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎭 SyncTalk Video Generator</h1>
                <p style="text-align: center; color: #666; font-size: 18px;">
                    Choose your preferred interface for generating talking face videos
                </p>
                <div class="button-group">
                    <a href="generate-page" class="btn btn-primary">
                        📄 Classic Mode<br>
                        <small style="font-size: 12px;">(New page for each video)</small>
                    </a>
                    <a href="live" class="btn btn-secondary">
                        🔄 Live Mode<br>
                        <small style="font-size: 12px;">(Update video in-place)</small>
                    </a>
                </div>
            </div>
        </body>
    </html>
    """)

@app.get("/generate-page")
async def generate_page():
    """Classic generation page"""
    return HTMLResponse("""
    <html>
        <head>
            <title>SyncTalk - Classic Mode</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 50px auto;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                }
                .container {
                    background: white;
                    border-radius: 10px;
                    padding: 30px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                }
                h1 {
                    color: #333;
                    text-align: center;
                }
                .form-group {
                    margin-bottom: 20px;
                }
                label {
                    display: block;
                    margin-bottom: 5px;
                    color: #555;
                    font-weight: bold;
                }
                input {
                    width: 100%;
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    box-sizing: border-box;
                }
                button {
                    width: 100%;
                    padding: 12px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    border-radius: 5px;
                    font-size: 16px;
                    cursor: pointer;
                    transition: opacity 0.3s;
                }
                button:hover {
                    opacity: 0.9;
                }
                .back-link {
                    display: block;
                    text-align: center;
                    margin-top: 20px;
                    color: #667eea;
                    text-decoration: none;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎭 SyncTalk Classic Mode</h1>
                <form action="/render" method="post" enctype="multipart/form-data">
                    <div class="form-group">
                        <label for="token">Authentication Token:</label>
                        <input type="text" name="token" value="supersecrettoken" required>
                    </div>
                    <div class="form-group">
                        <label for="wav">Audio File (WAV):</label>
                        <input type="file" name="wav" accept=".wav" required>
                    </div>
                    <button type="submit">Generate Video</button>
                </form>
                <a href="/" class="back-link">← Back to Home</a>
            </div>
        </body>
    </html>
    """)

@app.get("/live")
async def live_page():
    """Live update page with ChatGPT→TTS, scrollable menu, gaze tracking + metrics, and autoplay"""
    return HTMLResponse("""
    <html>
        <head>
            <title>SyncTalk - Live Mode (ChatGPT → TTS + Gaze)</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh; padding: 20px;
                }
                .container { max-width: 1400px; margin: 0 auto; }
                .header { text-align: center; color: white; margin-bottom: 30px; }
                .header h1 { font-size: 2.5em; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
                .main-content { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 20px; }
                .panel {
                    background: white; border-radius: 15px; padding: 25px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    display: flex; flex-direction: column;
                }

                /* Scrollable menu container (left panel, above prompt) */
                .menu-section {
                    max-height: 50vh;               /* fixed area, independently scrollable */
                    overflow-y: auto;
                    padding: 12px 12px 12px 16px;
                    margin-bottom: 20px;
                    border: 1px solid #eee;
                    border-radius: 10px;
                    background: #fafafa;
                }
                .menu-section h3 {
                    color: #333; margin: 4px 0 12px; font-size: 1.4em;
                    text-align: center; position: sticky; top: 0;
                    background: #fafafa; padding: 8px 0; z-index: 5;
                }
                .menu-item {
                    margin-bottom: 16px;
                    border: 1px solid #e5e5e5; border-radius: 10px;
                    padding: 14px 12px; background: #fff;
                    transition: box-shadow 120ms ease, transform 120ms ease, border-color 120ms ease;
                    min-height: 110px;
                }
                .menu-item:hover { border-color: #d8e7f7; }
                .menu-item h4 {
                    display: flex; justify-content: space-between;
                    margin: 0 0 6px; font-size: 1.05rem;
                }
                .menu-item p { margin: 0; color: #555; font-size: 0.95rem; line-height: 1.4; }
                .menu-item.highlight {
                    box-shadow: 0 0 0 3px rgba(0,120,255,0.35);
                    transform: translateY(-1px);
                }

                .form-section h2 {
                    color: #333; margin: 10px 0 15px; font-size: 1.4em; text-align: center;
                }
                .form-group { margin-bottom: 20px; }
                .form-group label { display: block; margin-bottom: 8px; color: #555; font-weight: 500; }
                .form-group textarea, .form-group input[type="text"] {
                    width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px;
                    font-size: 16px; transition: border-color 0.3s; resize: vertical; min-height: 120px;
                }
                .form-group textarea:focus, .form-group input:focus { outline: none; border-color: #667eea; }

                .generate-btn {
                    width: 100%; padding: 15px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; border: none; border-radius: 8px;
                    font-size: 18px; font-weight: 600;
                    cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;
                }
                .generate-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102,126,234,0.4); }
                .generate-btn:disabled { opacity: 0.7; cursor: not-allowed; }

                .status-bar {
                    margin-top: 15px; padding: 10px; background: #f0f0f0;
                    border-radius: 8px; text-align: center; font-size: 14px;
                }
                .status-processing { background: #fff3cd; color: #856404; }
                .status-success { background: #d4edda; color: #155724; }
                .status-error { background: #f8d7da; color: #721c24; }
                .loading-spinner {
                    display: inline-block; width: 20px; height: 20px; margin-right: 10px;
                    border: 3px solid rgba(0,0,0,0.1); border-radius: 50%; border-top-color: #667eea; animation: spin 1s ease-in-out infinite;
                }
                @keyframes spin { to { transform: rotate(360deg); } }

                .video-section { position: relative; }
                .video-container {
                    background: #f5f5f5; border-radius: 10px; padding: 20px;
                    min-height: 400px; display: flex; align-items: center; justify-content: center;
                }
                video { width: 100%; max-width: 100%; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
                .placeholder { text-align: center; color: #999; }
                .placeholder svg { width: 100px; height: 100px; margin-bottom: 20px; opacity: 0.3; }

                @media (max-width: 768px) { .main-content { grid-template-columns: 1fr; } }
                .back-link { display: block; text-align: center; margin-top: 20px; color: white; text-decoration: none; }
                .back-link:hover { text-decoration: underline; }
                .generated-text { margin-top: 10px; font-size: 14px; color: #555; text-align: center; }

                /* Gaze dot (debug; hidden by default) */
                .gaze-dot {
                    position: fixed; width: 8px; height: 8px; border-radius: 50%;
                    background: red; pointer-events: none; z-index: 99999;
                    transform: translate(-50%, -50%); display: none;
                }

                /* Calibration overlay */
                .calib-backdrop {
                    position: fixed; inset: 0; background: rgba(0,0,0,0.5);
                    display: flex; align-items: center; justify-content: center; z-index: 99998;
                }
                .calib-card {
                  position: relative;
                  width: 96vw; max-width: 1400px;
                  background: #fff; border-radius: 12px; padding: 16px 16px 22px;
                  box-shadow: 0 10px 30px rgba(0,0,0,0.25);
                }
                .calib-title { margin: 0 0 6px; font-size: 1.15rem; }
                .calib-desc { margin: 0 0 12px; color: #555; font-size: 0.95rem; }
                .calib-stage {
                  position: relative;
                  width: 100%;
                  height: min(78vh, 900px); /* tall, but not past viewport on small laptops */
                  border: 1px dashed #ddd; border-radius: 10px; background: #fafafa; overflow: hidden;
                }
                /* Larger, easier-to-click dots */
                .calib-dot {
                  position: absolute; width: 22px; height: 22px; border-radius: 50%;
                  background: #0077cc; box-shadow: 0 0 0 6px rgba(0,119,204,0.18);
                  cursor: pointer; transform: translate(-50%, -50%);
                  transition: transform 120ms ease, background 120ms ease, box-shadow 120ms ease;
                }
                .calib-dot.done {
                  background: #2e7d32; box-shadow: 0 0 0 6px rgba(46,125,50,0.18);
                  transform: translate(-50%, -50%) scale(0.9);
                }
                .calib-footer {
                    display: flex; align-items: center; gap: 12px; margin-top: 12px;
                    justify-content: space-between; flex-wrap: wrap;
                }
                .calib-progress { flex: 1; height: 10px; background: #eee; border-radius: 999px; overflow: hidden; min-width: 160px; }
                .calib-bar { height: 100%; width: 0%; background: linear-gradient(90deg, #0077cc, #00a1ff); }
                .btn-secondary { background: #e9eef3; color: #0d3a5c; border: 1px solid #c9d7e3; }
                .btn-secondary:hover { background: #dfe8ef; }
                .hidden { display: none !important; }

                /* Inline metrics (below video on the right) */
                .metrics {
                    width: 100%;
                    background: rgba(255,255,255,0.92);
                    border: 1px solid #dcdcdc;
                    border-radius: 10px;
                    box-shadow: 0 4px 18px rgba(0,0,0,0.08);
                    padding: 12px 12px 8px;
                    backdrop-filter: blur(2px);
                    margin-top: 16px;   /* space above metrics under the video */
                  }
                .metrics h4 { margin: 0 0 8px; font-size: 0.95rem; color: #0f3057; }
                .metric-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; margin: 6px 0; }
                .metric-label { font-size: 0.9rem; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .metric-time { font-variant-numeric: tabular-nums; font-size: 0.9rem; color: #222; }
                .metric-bar { grid-column: 1 / -1; height: 6px; background: #eee; border-radius: 999px; overflow: hidden; }
                .metric-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #6fb1ff, #1e90ff); transition: width 200ms linear; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎭 SyncTalk Live Mode</h1>
                    <p>Type a prompt → ChatGPT crafts a reply → we speak it and animate a talking head.</p>
                </div>

                <div class="main-content">
                    <!-- LEFT PANEL -->
                    <div class="panel form-section">
                        <!-- Scrollable Menu -->
                        <div style="text-align:right; margin: 6px 0 12px;">
                          <button id="recalBtn" class="btn-secondary" style="padding:6px 10px; border-radius:6px; cursor:pointer;">
                            Recalibrate
                          </button>
                        </div>
                        <div class="menu-section" id="menuSection">
                            <h3>Today's Menu</h3>

                            <div class="menu-item"><h4>Margherita Pizza <span>$12</span></h4><p>Classic pizza with tomato sauce, mozzarella, and fresh basil leaves.</p></div>
                            <div class="menu-item"><h4>Grilled Salmon <span>$18</span></h4><p>Perfectly grilled salmon served with lemon butter sauce and roasted vegetables.</p></div>
                            <div class="menu-item"><h4>Caesar Salad <span>$10</span></h4><p>Crisp romaine lettuce tossed in creamy Caesar dressing with parmesan and croutons.</p></div>
                            <div class="menu-item"><h4>Spaghetti Carbonara <span>$14</span></h4><p>Rich and creamy pasta with pancetta, egg yolk, and parmesan cheese.</p></div>
                            <div class="menu-item"><h4>Chocolate Lava Cake <span>$8</span></h4><p>Warm chocolate cake with a molten center, served with vanilla ice cream.</p></div>

                            <div class="menu-item"><h4>Cabernet Sauvignon <span>$9 / glass</span></h4><p>Full-bodied red wine with notes of dark cherry, oak, and a hint of vanilla.</p></div>
                            <div class="menu-item"><h4>Pinot Grigio <span>$8 / glass</span></h4><p>Crisp white wine offering bright flavors of green apple, pear, and citrus.</p></div>
                            <div class="menu-item"><h4>Rosé Blend <span>$8 / glass</span></h4><p>Refreshing and light, with aromas of strawberry and watermelon — perfect for summer evenings.</p></div>
                        </div>

                        <!-- Prompt Form -->
                        <h2>📝 Enter Prompt</h2>
                        <form id="textForm">
                            <div class="form-group">
                                <label for="prompt">What should ChatGPT answer (we'll speak the answer)?</label>
                                <textarea id="prompt" placeholder="e.g., Describe the flavors of each wine on the menu."></textarea>
                            </div>
                            <button type="submit" class="generate-btn" id="generateBtn">Generate Talking Video</button>
                        </form>
                        <div id="statusBar" class="status-bar" style="display: none;"></div>
                    </div>

                    <!-- RIGHT PANEL: Video -->
                    <div class="panel video-section">
                        <h2>🎬 Generated Video</h2>
                        <div class="video-container">
                            <div id="videoPlaceholder" class="placeholder">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
                                    <line x1="7" y1="2" x2="7" y2="22"></line>
                                    <line x1="17" y1="2" x2="17" y2="22"></line>
                                    <line x1="2" y1="12" x2="22" y2="12"></line>
                                </svg>
                                <p>Your generated video will appear here</p>
                                <p style="font-size: 12px; margin-top: 10px;">Type a prompt and click Generate</p>
                            </div>
                            <video id="videoPlayer" controls autoplay muted style="display: none;"></video>
                        </div>
                        <div id="videoStatus" style="margin-top: 10px; text-align: center; color: #666;"></div>
                        <div id="generatedText" class="generated-text"></div>
                        <!-- ✅ Metrics now lives here, below the video -->
                        <div id="metrics" class="metrics">
                            <h4>Gaze Dwell (seconds)</h4>
                            <div id="metricsList"></div>
                        </div>
                    </div>
                </div>

                <a href="/" class="back-link">← Back to Home</a>
            </div>

            <!-- Gaze debug dot -->
            <div id="gazeDot" class="gaze-dot"></div>

            <!-- Calibration Overlay -->
            <div id="calibOverlay" class="calib-backdrop">
                <div class="calib-card">
                    <h4 class="calib-title">Quick Calibration</h4>
                    <p class="calib-desc">We’ll use your webcam to estimate where you’re looking (processed locally in your browser).
                        Click each dot once. When all 5 are green, click <b>Finish</b>.</p>

                    <div class="calib-stage" id="calibStage">
                      <!-- Row 1 -->
                      <div class="calib-dot" data-key="tl"  style="left:5%;  top:8%;"></div>
                      <div class="calib-dot" data-key="tc"  style="left:50%; top:8%;"></div>
                      <div class="calib-dot" data-key="tr"  style="left:95%; top:8%;"></div>
                      <!-- Row 2 -->
                      <div class="calib-dot" data-key="cl"  style="left:5%;  top:50%;"></div>
                      <div class="calib-dot" data-key="cc"  style="left:50%; top:50%;"></div>
                      <div class="calib-dot" data-key="cr"  style="left:95%; top:50%;"></div>
                      <!-- Row 3 -->
                      <div class="calib-dot" data-key="bl"  style="left:5%;  top:92%;"></div>
                      <div class="calib-dot" data-key="bc"  style="left:50%; top:92%;"></div>
                      <div class="calib-dot" data-key="br"  style="left:95%; top:92%;"></div>
                    </div>

                    <div class="calib-footer">
                        <div class="calib-progress"><div id="calibBar" class="calib-bar"></div></div>
                        <div class="calib-actions">
                            <button id="retryBtn" class="btn-secondary">Reset</button>
                            <button id="finishBtn">Finish</button>
                        </div>
                        <div class="calib-note">Tip: keep your head steady and sit ~arm’s length from the screen.</div>
                    </div>
                </div>
            </div>

            <!-- WebGazer (HTTPS or localhost required) -->
            <script src="https://cdn.jsdelivr.net/npm/webgazer/dist/webgazer.min.js"></script>

            <script>
                /* ---------- Live page: ChatGPT->TTS flow ---------- */
                const BASE = new URL(window.location.href);
                const form = document.getElementById('textForm');
                const promptEl = document.getElementById('prompt');
                const tokenEl = document.getElementById('token');
                const btn = document.getElementById('generateBtn');
                const statusBar = document.getElementById('statusBar');
                const video = document.getElementById('videoPlayer');
                const placeholder = document.getElementById('videoPlaceholder');
                const videoStatus = document.getElementById('videoStatus');
                const generatedText = document.getElementById('generatedText');

                function showStatus(message, type='processing') {
                    statusBar.style.display = 'block';
                    statusBar.className = 'status-bar status-' + type;
                    if (type === 'processing') {
                        statusBar.innerHTML = '<span class="loading-spinner"></span>' + message;
                    } else {
                        statusBar.textContent = message;
                    }
                }
                function hideStatusSoon() { setTimeout(() => { statusBar.style.display = 'none'; }, 3000); }

                async function pollStatus(taskId) {
                    const interval = setInterval(async () => {
                        try {
                            const url = new URL('status/' + taskId, BASE);
                            const res = await fetch(url);
                            const data = await res.json();

                            if (data.status === 'completed') {
                                clearInterval(interval);
                                showStatus('Video generated successfully!', 'success');

                                video.src = data.video_url + '?t=' + Date.now();
                                video.style.display = 'block';
                                placeholder.style.display = 'none';
                                videoStatus.textContent = 'Generated at ' + new Date().toLocaleTimeString();
                                generatedText.textContent = data.generated_text ? ('🗨️ Script: ' + data.generated_text) : '';

                                /* Autoplay when ready */
                                video.autoplay = true;
                                // If you'd like sound immediately, set muted=false; otherwise keep muted to guarantee autoplay.
                                // video.muted = false;
                                video.play().catch(err => console.warn('Autoplay blocked:', err));

                                btn.disabled = false; btn.textContent = 'Generate Talking Video';
                                hideStatusSoon();
                            } else if (data.status === 'error') {
                                clearInterval(interval);
                                showStatus('Error: ' + data.message, 'error');
                                btn.disabled = false; btn.textContent = 'Generate Talking Video';
                            } else {
                                showStatus((data.message || 'Processing...') + (data.progress ? (' ' + data.progress + '%') : ''), 'processing');
                            }
                        } catch (e) { console.error('Poll error', e); }
                    }, 2000);
                }

                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const prompt = (promptEl.value || '').trim();
                    if (!prompt) { showStatus('Please enter a prompt.', 'error'); return; }
                    if (!tokenEl.value) { showStatus('Missing token.', 'error'); return; }

                    btn.disabled = true; btn.textContent = 'Generating...';
                    showStatus('Starting ChatGPT pipeline...', 'processing');
                    generatedText.textContent = '';

                    try {
                        const formData = new FormData();
                        formData.append('prompt', prompt);
                        formData.append('token', tokenEl.value);
                        const url = new URL('generate-from-text-async', BASE);
                        const res = await fetch(url, { method: 'POST', body: formData });

                        if (!res.ok) throw new Error(await res.text() || 'Failed to start generation');
                        const data = await res.json();
                        showStatus('Processing...', 'processing');
                        pollStatus(data.task_id);
                    } catch (err) {
                        console.error(err);
                        showStatus('Error: ' + err.message, 'error');
                        btn.disabled = false; btn.textContent = 'Generate Talking Video';
                    }
                });

                /* ---------- Gaze tracking + metrics ---------- */
                const items = Array.from(document.querySelectorAll('.menu-item'));
                const labels = items.map(el => el.querySelector('h4')?.childNodes?.[0]?.textContent.trim() || 'Item');
                const gazeDot = document.getElementById('gazeDot');

                // --------- Smoothing (EMA) ----------
                let smX = null, smY = null;
                const SMOOTH_ALPHA = 0.25; // 0.15-0.35 works; higher = snappier
                function smoothXY(x, y) {
                  if (smX == null) { smX = x; smY = y; }
                  else { smX = smX + SMOOTH_ALPHA * (x - smX);
                         smY = smY + SMOOTH_ALPHA * (y - smY); }
                  return [smX, smY];
                }
                
                // --------- Hysteresis (require stability before switching) ----------
                let stableIdx = -1;
                let stableFrames = 0;
                const STABLE_FRAMES_N = 6;  // ~6 frames ~ 100ms depending on WebGazer rate
                
                // --------- Expand hitboxes slightly ----------
                function expandBBox(b, pct = 0.12) {
                  const dx = b.w * pct, dy = b.h * pct;
                  return { x: b.x - dx, y: b.y - dy, w: b.w + 2*dx, h: b.h + 2*dy };
                }
                
                // --------- Implicit calibration on dwell ----------
                const IMPLICIT_DWELL_MS = 1500; // after 1.5s dwell, add a labeled sample
                let lastImplicitStamp = 0;
                
                // Helper: record N samples at (x,y)
                function recordSamples(x, y, n = 10, interval = 8) {
                  if (!webgazer || !webgazer.recordScreenPosition) return;
                  const start = performance.now();
                  for (let i = 0; i < n; i++) {
                    setTimeout(() => webgazer.recordScreenPosition(x, y, performance.now()), i * interval);
                  }
                }

                // Dwell accumulation (ms) per item
                const dwell = new Array(items.length).fill(0);
                let lastTs = null;
                let currentIdx = -1;

                // Metrics UI build
                const metricsList = document.getElementById('metricsList');
                const rows = labels.map((label, i) => {
                    const row = document.createElement('div');
                    row.className = 'metric-row';

                    const name = document.createElement('div');
                    name.className = 'metric-label';
                    name.textContent = label;

                    const time = document.createElement('div');
                    time.className = 'metric-time';
                    time.textContent = '0.0s';

                    const bar = document.createElement('div');
                    bar.className = 'metric-bar';
                    const fill = document.createElement('div');
                    fill.className = 'metric-fill';
                    bar.appendChild(fill);

                    row.appendChild(name);
                    row.appendChild(time);
                    row.appendChild(bar);
                    metricsList.appendChild(row);
                    return {row, time, fill};
                });

                function updateMetrics() {
                    const max = Math.max(...dwell, 1);
                    for (let i = 0; i < dwell.length; i++) {
                        const seconds = dwell[i] / 1000;
                        rows[i].time.textContent = seconds.toFixed(1) + 's';
                        const pct = Math.min(100, (dwell[i] / max) * 100);
                        rows[i].fill.style.width = pct + '%';
                    }
                }

                function bbox(el) {
                    const r = el.getBoundingClientRect();
                    return { x: r.left, y: r.top, w: r.width, h: r.height };
                }
                function contains(b, x, y) {
                    return x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h;
                }
                function highlightIdx(idx) {
                    items.forEach(i => i.classList.remove('highlight'));
                    if (idx >= 0) items[idx].classList.add('highlight');
                }

                /* ---------- Calibration overlay ---------- */

                function lockScroll() { document.body.dataset.prevOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; }
                function unlockScroll() { document.body.style.overflow = document.body.dataset.prevOverflow || ''; }

                const overlay = document.getElementById('calibOverlay');
                const dots = Array.from(document.querySelectorAll('.calib-dot'));
                const bar = document.getElementById('calibBar');
                const finishBtn = document.getElementById('finishBtn');
                const retryBtn = document.getElementById('retryBtn');

                let done = new Set();
                function updateBar() {
                    const pct = Math.round((done.size / dots.length) * 100);
                    bar.style.width = pct + '%';
                }
                function resetCalibration() {
                    done.clear();
                    dots.forEach(d => d.classList.remove('done'));
                    updateBar();
                }

                // Take a bigger burst of samples — improves the regression fit
                function recordSamples(x, y, n = 24, interval = 6) {
                  if (!webgazer || !webgazer.recordScreenPosition) return;
                  for (let i = 0; i < n; i++) {
                    setTimeout(() => webgazer.recordScreenPosition(x, y, performance.now()), i * interval);
                  }
                }

                dots.forEach(dot => {
                  dot.addEventListener('click', () => {
                    dot.classList.add('done');
                    done.add(dot.dataset.key);
                    updateBar();
                
                    const r = dot.getBoundingClientRect();
                    const cx = r.left + r.width/2;
                    const cy = r.top  + r.height/2;
                
                    // Burst of labeled samples at this target (more = better fit)
                    recordSamples(cx, cy, 28, 5);
                  });
                });

                // When opening calibration from your Recalibrate button/hotkey:
                document.getElementById('recalBtn')?.addEventListener('click', () => {
                  overlay.classList.remove('hidden'); resetCalibration(); lockScroll();
                });
                document.addEventListener('keydown', (e) => {
                  if (e.key.toLowerCase() === 'c') { overlay.classList.remove('hidden'); resetCalibration(); lockScroll(); }
                });
                
                finishBtn.addEventListener('click', () => {
                  if (done.size < dots.length) { alert('Please click all nine dots to complete calibration.'); return; }
                  overlay.classList.add('hidden'); unlockScroll();
                  startGaze(); // your existing function
                });

                retryBtn.addEventListener('click', resetCalibration);
                
                document.getElementById('recalBtn').addEventListener('click', () => {
                  overlay.classList.remove('hidden');
                  resetCalibration();
                });
                
                // Hotkey 'c' to open calibration quickly
                document.addEventListener('keydown', (e) => {
                  if (e.key.toLowerCase() === 'c') {
                    overlay.classList.remove('hidden');
                    resetCalibration();
                  }
                });


                finishBtn.addEventListener('click', () => {
                    if (done.size < dots.length) {
                        alert('Please click all five dots to complete calibration.');
                        return;
                    }
                    overlay.classList.add('hidden');
                    startGaze();
                });

                /* ---------- WebGazer init ---------- */
                (async function initWebGazer(){
                    try {
                        if (webgazer.addMouseEventListeners) webgazer.addMouseEventListeners();
                        await webgazer.begin();

                        // Hide WebGazer default overlays if present
                        const hide = id => { const n = document.getElementById(id); if (n) n.style.display = 'none'; };
                        hide('webgazerVideoContainer');
                        hide('webgazerGazeDot');

                        console.log('WebGazer initialized.');
                    } catch (e) {
                        console.error('WebGazer failed to start:', e);
                        alert('Could not start camera. Please use HTTPS or localhost and allow camera access.');
                    }
                })();

                /* ---------- Start gaze listener ---------- */
                const DWELL_ACTIVATE_MS = 600; // highlight dwell threshold
                function startGaze() {
                  if (webgazer.setRegression) webgazer.setRegression('ridge');
                
                  webgazer.setGazeListener((data, ts) => {
                    if (!data) { lastTs = ts; return; }
                
                    // 1) Smooth the point
                    const [x, y] = smoothXY(data.x, data.y);
                
                    // (Optional) debug dot
                    // gazeDot.style.left = x + 'px';
                    // gazeDot.style.top  = y + 'px';
                
                    // 2) Which item under gaze? Use expanded hitboxes
                    const overIdxRaw = items.findIndex(el => {
                      const eb = expandBBox(bbox(el));   // expanded
                      return contains(eb, x, y);
                    });
                
                    // 3) Hysteresis: require a few frames on the same item
                    if (overIdxRaw === stableIdx) {
                      stableFrames++;
                    } else {
                      stableIdx = overIdxRaw;
                      stableFrames = 1;
                    }
                    const overIdx = (stableFrames >= STABLE_FRAMES_N) ? stableIdx : -1;
                
                    // 4) Accumulate dwell against the *currentIdx* we consider active
                    if (lastTs != null && currentIdx >= 0) {
                      const dt = Math.max(0, ts - lastTs);
                      dwell[currentIdx] += dt;
                    }
                    lastTs = ts;
                
                    // 5) Switch logic + highlight after dwell threshold
                    if (overIdx !== currentIdx) {
                      currentIdx = overIdx;
                      highlightIdx(-1);
                      return;
                    } else {
                      if (currentIdx >= 0) {
                        const currentDwell = dwell[currentIdx];
                        const isHighlighted = items[currentIdx].classList.contains('highlight');
                        if (!isHighlighted && currentDwell >= DWELL_ACTIVATE_MS) {
                          highlightIdx(currentIdx);
                        }
                
                        // 6) Implicit calibration once per item every IMPLICIT_DWELL_MS
                        const now = performance.now();
                        if (currentDwell >= IMPLICIT_DWELL_MS && (now - lastImplicitStamp) > 800) {
                          const r = items[currentIdx].getBoundingClientRect();
                          const cx = r.left + r.width/2;
                          const cy = r.top  + r.height/2;
                          recordSamples(cx, cy, /*n=*/12, /*interval=*/8);
                          lastImplicitStamp = now;
                        }
                      } else {
                        highlightIdx(-1);
                      }
                    }
                  });
                
                  // Metrics refresh loop (unchanged)
                  function metricsLoop() {
                    updateMetrics();
                    requestAnimationFrame(metricsLoop);
                  }
                  metricsLoop();
                }
            </script>
        </body>
    </html>
    """)

@app.post("/generate-async")
async def generate_async(token: str = Form(...), wav: UploadFile = File(...)):
    """Start async video generation and return task ID"""
    
    if token != "supersecrettoken":
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Generate unique task ID
    task_id = str(uuid.uuid4())
    
    # Save uploaded file
    temp_audio_path = f"temp_uploads/{task_id}_audio.wav"
    with open(temp_audio_path, "wb") as f:
        f.write(await wav.read())
    
    # Initialize task status
    active_tasks[task_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Starting video generation...",
        "video_url": None
    }
    
    # Start generation in background
    thread = threading.Thread(target=generate_video_background, args=(task_id, temp_audio_path))
    thread.start()
    
    return {"task_id": task_id, "status": "started"}

@app.post("/generate-from-text-async")
async def generate_from_text_async(
    token: str = Form(...),
    prompt: str = Form(...)
):
    """Start async ChatGPT->TTS->Video generation and return task ID."""
    if token != "supersecrettoken":
        raise HTTPException(status_code=401, detail="Invalid token")

    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    task_id = str(uuid.uuid4())

    active_tasks[task_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Starting ChatGPT pipeline...",
        "video_url": None,
        "generated_text": None,
    }

    thread = threading.Thread(target=generate_text_video_background, args=(task_id, prompt))
    thread.start()

    return {"task_id": task_id, "status": "started"}

@app.get("/status/{task_id}")
async def check_status(task_id: str):
    """Check the status of a generation task"""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return active_tasks[task_id]

@app.post("/render")
async def render(token: str = Form(...), wav: UploadFile = File(...)):
    """Classic render endpoint (original functionality)"""
    
    if token != "supersecrettoken":
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Save uploaded file temporarily
    temp_audio_path = "temp_audio.wav"
    with open(temp_audio_path, "wb") as f:
        f.write(await wav.read())
    
    try:
        ensure_assets()
        
        # Run SyncTalk generation
        cmd = [
            sys.executable, str(PROJECT_ROOT / "main.py"),
            str(DATA_ROOT),
            "--workspace", str(WORKSPACE),
            "-O", "--test", "--test_train",
            "--asr_model", "ave",
            "--portrait",
            "--aud", temp_audio_path
        ]
        
        # Ensure imports resolve
        child_env = os.environ.copy()
        child_env["PYTHONPATH"] = f"{PROJECT_ROOT}:{child_env.get('PYTHONPATH','')}"
        
        result = subprocess.run(cmd, capture_output=True, text=True, env=child_env)
        
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Generation failed: {result.stderr}")
        
        # Find and return the generated video
        out_path = latest_audio_mp4(RESULTS_DIR)
        return FileResponse(str(out_path), media_type="video/mp4")
            
    finally:
        # Clean up
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

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

    out_path = latest_audio_mp4(RESULTS_DIR)
    rel_url = f"/results/{out_path.name}"
    cache_bust = uuid.uuid4().hex  # force fresh load

    return HTMLResponse(f"""
    <html>
      <body style='font-family:system-ui'>
        <h3>Input:</h3><p>{text}</p>

        <h3>Output video:</h3>
        <video id="vid" controls width="640"
           src="{rel_url}?v={cache_bust}"
           preload="metadata">
          Your browser does not support MP4 playback.
        </video>

        <p><a id="dl" href="{rel_url}" download>Download video</a></p>

        <script>
          // Log the URL we're trying to play (helps you confirm in the console)
          console.log("Playing:", "{rel_url}?v={cache_bust}");
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

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
