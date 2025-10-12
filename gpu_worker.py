# gpu_worker.py
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
import os, uuid, subprocess, shlex, glob

app = FastAPI()
PROJECT_ROOT="/app"
DATA_ROOT=f"{PROJECT_ROOT}/data/May"
WORKSPACE=f"{PROJECT_ROOT}/model/trial_may"
OUT_DIR=f"{WORKSPACE}/results"
os.makedirs(OUT_DIR, exist_ok=True)

@app.post("/render")
async def render(text: str = Form(None), wav: UploadFile = File(None)):
    # write wav
    wav_path = f"{PROJECT_ROOT}/demo/{uuid.uuid4().hex}.wav"
    os.makedirs(f"{PROJECT_ROOT}/demo", exist_ok=True)
    if wav:
        with open(wav_path, "wb") as f:
            f.write(await wav.read())
    else:
        return JSONResponse({"error":"no wav"}, status_code=400)

    cmd = f"python {PROJECT_ROOT}/main.py {DATA_ROOT} --workspace {WORKSPACE} -O --test --test_train --asr_model ave --portrait --aud {wav_path}"
    proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True)
    if proc.returncode != 0:
        return JSONResponse({"error":"render failed", "stderr": proc.stderr[-4000:]}, status_code=500)

    mp4s = glob.glob(f"{OUT_DIR}/*.mp4")
    if not mp4s:
        return JSONResponse({"error":"no mp4"}, status_code=500)
    newest = max(mp4s, key=os.path.getmtime)
    return FileResponse(newest, media_type="video/mp4", filename=os.path.basename(newest))
