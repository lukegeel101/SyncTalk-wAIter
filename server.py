from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse, HTMLResponse
import subprocess, uuid, os, shlex, glob

app = FastAPI()

# Paths – adjust to match your Colab project structure
PROJECT_ROOT = "/app"
DATA_ROOT    = f"{PROJECT_ROOT}/data/May"              # ABSOLUTE now
DEMO_DIR = f"{PROJECT_ROOT}/demo"
WORKSPACE = f"{PROJECT_ROOT}/model/trial_may"
RESULTS_DIR = f"{WORKSPACE}/results"
os.makedirs(DEMO_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


GDRIVE_DATA_ID  = "18Q2H612CAReFxBd9kxr-i1dD8U1AUfsV"  # May.zip
GDRIVE_MODEL_ID = "1C2639qi9jvhRygYHwPZDGs8pun3po3W7"  # trial_may.zip


def ensure_assets():
    """Download & unzip data/May and model/trial_may if missing."""
    # We’ll use gdown (install in Dockerfile/requirements)
    def _need(path): return not os.path.exists(path)
    def _dl_and_unzip(file_id: str, out_zip: str, dest_dir: str):
        os.makedirs(os.path.dirname(out_zip), exist_ok=True)
        # download
        subprocess.run(["gdown", "--fuzzy", f"https://drive.google.com/uc?id={file_id}", "-O", out_zip],
                       check=True)
        # unzip
        os.makedirs(dest_dir, exist_ok=True)
        subprocess.run(["unzip", "-o", out_zip, "-d", os.path.dirname(dest_dir)], check=True)
        # optional: remove zip
        try: os.remove(out_zip)
        except: pass

    # data/May
    if _need(DATA_ROOT):
        _dl_and_unzip(GDRIVE_DATA_ID, f"{PROJECT_ROOT}/data/May.zip", f"{PROJECT_ROOT}/data")
    # model/trial_may
    if _need(WORKSPACE):
        _dl_and_unzip(GDRIVE_MODEL_ID, f"{PROJECT_ROOT}/model/trial_may.zip", f"{PROJECT_ROOT}/model")

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
    wav_path = os.path.join(DEMO_DIR, "input.wav")

    
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
    cmd = f"python {PROJECT_ROOT}/main.py {DATA_ROOT} --workspace {WORKSPACE} -O --test --test_train --asr_model ave --portrait --aud {wav_path}"
    subprocess.run(shlex.split(cmd), check=True)

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
