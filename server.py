from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
import subprocess, uuid, os, shlex, glob, shutil, sys
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import time
import uvicorn
import tempfile

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

print("[BOOT] PROJECT_ROOT:", PROJECT_ROOT)
print("[BOOT] DATA_ROOT:", DATA_ROOT, "exists:", DATA_ROOT.is_dir())
print("[BOOT] WORKSPACE:", WORKSPACE, "exists:", WORKSPACE.is_dir())

# Mount directories for serving files
if os.path.exists("demo"):
    app.mount("/demo", StaticFiles(directory="demo"), name="demo")
if os.path.exists("results"):
    app.mount("/results", StaticFiles(directory="results"), name="results")

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

def generate_video_background(task_id, audio_path):
    """Background task for video generation"""
    try:
        # Update progress
        active_tasks[task_id]["progress"] = 10
        active_tasks[task_id]["message"] = "Processing audio..."
        
        # Run SyncTalk generation
        output_path = f"results/output_{task_id}.mp4"
        
        # Simulate different progress stages
        active_tasks[task_id]["progress"] = 30
        active_tasks[task_id]["message"] = "Generating facial expressions..."
        
        cmd = [
            "python3.8", "main.py", "data/May",
            "--workspace", "model/trial_may",
            "-O", "--test", "--test_train",
            "--asr_model", "ave",
            "--portrait",
            "--aud", audio_path,
            "--output", output_path
        ]
        
        # Run the actual command
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        active_tasks[task_id]["progress"] = 80
        active_tasks[task_id]["message"] = "Finalizing video..."
        
        if result.returncode != 0:
            raise Exception(f"Generation failed: {result.stderr}")
        
        # Find the generated video
        import glob
        video_files = glob.glob(f"model/trial_may/results/*_vocal.mp4")
        if video_files:
            # Copy to results directory
            shutil.copy(video_files[-1], output_path)
            
            active_tasks[task_id]["status"] = "completed"
            active_tasks[task_id]["progress"] = 100
            active_tasks[task_id]["message"] = "Video generated successfully"
            active_tasks[task_id]["video_url"] = f"/results/{os.path.basename(output_path)}"
        else:
            raise Exception("No output video found")
            
    except Exception as e:
        active_tasks[task_id]["status"] = "error"
        active_tasks[task_id]["message"] = str(e)
    finally:
        # Clean up temp file
        if os.path.exists(audio_path):
            os.remove(audio_path)

# Store active tasks
active_tasks = {}

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
    
    # Start generation in background (you'd normally use asyncio.create_task or threading)
    import threading
    thread = threading.Thread(target=generate_video_background, args=(task_id, temp_audio_path))
    thread.start()
    
    return {"task_id": task_id, "status": "started"}

@app.get("/generate-page")
async def generate_page():
    """Classic generation page (original functionality)"""
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
    """Live update page where video updates in-place"""
    return HTMLResponse("""
    <html>
        <head>
            <title>SyncTalk - Live Mode</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }
                .container {
                    max-width: 1400px;
                    margin: 0 auto;
                }
                .header {
                    text-align: center;
                    color: white;
                    margin-bottom: 30px;
                }
                .header h1 {
                    font-size: 2.5em;
                    margin-bottom: 10px;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                }
                .main-content {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 30px;
                    margin-bottom: 20px;
                }
                .panel {
                    background: white;
                    border-radius: 15px;
                    padding: 25px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                }
                .form-section h2 {
                    color: #333;
                    margin-bottom: 20px;
                    font-size: 1.5em;
                }
                .form-group {
                    margin-bottom: 20px;
                }
                .form-group label {
                    display: block;
                    margin-bottom: 8px;
                    color: #555;
                    font-weight: 500;
                }
                .form-group input[type="file"],
                .form-group input[type="text"] {
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #e0e0e0;
                    border-radius: 8px;
                    font-size: 16px;
                    transition: border-color 0.3s;
                }
                .form-group input:focus {
                    outline: none;
                    border-color: #667eea;
                }
                .file-input-wrapper {
                    position: relative;
                }
                .file-info {
                    margin-top: 5px;
                    font-size: 14px;
                    color: #666;
                }
                .generate-btn {
                    width: 100%;
                    padding: 15px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 18px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: transform 0.2s, box-shadow 0.2s;
                }
                .generate-btn:hover:not(:disabled) {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
                }
                .generate-btn:disabled {
                    opacity: 0.7;
                    cursor: not-allowed;
                }
                .video-section {
                    position: relative;
                }
                .video-container {
                    background: #f5f5f5;
                    border-radius: 10px;
                    padding: 20px;
                    min-height: 400px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                video {
                    width: 100%;
                    max-width: 100%;
                    border-radius: 8px;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                }
                .placeholder {
                    text-align: center;
                    color: #999;
                }
                .placeholder svg {
                    width: 100px;
                    height: 100px;
                    margin-bottom: 20px;
                    opacity: 0.3;
                }
                .status-bar {
                    margin-top: 15px;
                    padding: 10px;
                    background: #f0f0f0;
                    border-radius: 8px;
                    text-align: center;
                    font-size: 14px;
                }
                .status-processing {
                    background: #fff3cd;
                    color: #856404;
                }
                .status-success {
                    background: #d4edda;
                    color: #155724;
                }
                .status-error {
                    background: #f8d7da;
                    color: #721c24;
                }
                .loading-spinner {
                    display: inline-block;
                    width: 20px;
                    height: 20px;
                    margin-right: 10px;
                    border: 3px solid rgba(0,0,0,0.1);
                    border-radius: 50%;
                    border-top-color: #667eea;
                    animation: spin 1s ease-in-out infinite;
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
                .progress-bar {
                    width: 100%;
                    height: 6px;
                    background: #e0e0e0;
                    border-radius: 3px;
                    overflow: hidden;
                    margin-top: 10px;
                }
                .progress-fill {
                    height: 100%;
                    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                    width: 0%;
                    transition: width 0.3s;
                    animation: shimmer 2s infinite;
                }
                @keyframes shimmer {
                    0% { opacity: 0.8; }
                    50% { opacity: 1; }
                    100% { opacity: 0.8; }
                }
                @media (max-width: 768px) {
                    .main-content {
                        grid-template-columns: 1fr;
                    }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎭 SyncTalk Live Mode</h1>
                    <p>Generate talking face videos with real-time updates</p>
                </div>
                
                <div class="main-content">
                    <div class="panel form-section">
                        <h2>📤 Upload Files</h2>
                        <form id="uploadForm">
                            <div class="form-group">
                                <label for="audioFile">🎵 Audio File (WAV)</label>
                                <div class="file-input-wrapper">
                                    <input type="file" id="audioFile" accept=".wav" required>
                                    <div class="file-info" id="audioInfo"></div>
                                </div>
                            </div>
                            
                            <div class="form-group">
                                <label for="token">🔐 Authentication Token</label>
                                <input type="text" id="token" placeholder="Enter your token" value="supersecrettoken" required>
                            </div>
                            
                            <button type="submit" class="generate-btn" id="generateBtn">
                                Generate Video
                            </button>
                        </form>
                        
                        <div id="statusBar" class="status-bar" style="display: none;"></div>
                    </div>
                    
                    <div class="panel video-section">
                        <h2>🎬 Generated Video</h2>
                        <div class="video-container">
                            <div id="videoPlaceholder" class="placeholder">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
                                    <line x1="7" y1="2" x2="7" y2="22"></line>
                                    <line x1="17" y1="2" x2="17" y2="22"></line>
                                    <line x1="2" y1="12" x2="22" y2="12"></line>
                                    <line x1="2" y1="7" x2="7" y2="7"></line>
                                    <line x1="2" y1="17" x2="7" y2="17"></line>
                                    <line x1="17" y1="17" x2="22" y2="17"></line>
                                    <line x1="17" y1="7" x2="22" y2="7"></line>
                                </svg>
                                <p>Your generated video will appear here</p>
                                <p style="font-size: 12px; margin-top: 10px;">Upload an audio file to get started</p>
                            </div>
                            <video id="videoPlayer" controls style="display: none;"></video>
                        </div>
                        <div id="videoStatus" style="margin-top: 15px; text-align: center; color: #666;"></div>
                    </div>
                </div>
            </div>
            
            <script>
                const form = document.getElementById('uploadForm');
                const audioFile = document.getElementById('audioFile');
                const audioInfo = document.getElementById('audioInfo');
                const generateBtn = document.getElementById('generateBtn');
                const statusBar = document.getElementById('statusBar');
                const videoPlayer = document.getElementById('videoPlayer');
                const videoPlaceholder = document.getElementById('videoPlaceholder');
                const videoStatus = document.getElementById('videoStatus');
                
                audioFile.addEventListener('change', (e) => {
                    if (e.target.files[0]) {
                        const file = e.target.files[0];
                        const sizeMB = (file.size / 1024 / 1024).toFixed(2);
                        audioInfo.textContent = `Selected: ${file.name} (${sizeMB} MB)`;
                    } else {
                        audioInfo.textContent = '';
                    }
                });
                
                function showStatus(message, type = 'processing') {
                    statusBar.style.display = 'block';
                    statusBar.className = 'status-bar status-' + type;
                    if (type === 'processing') {
                        statusBar.innerHTML = '<span class="loading-spinner"></span>' + message;
                        if (message.includes('%')) {
                            statusBar.innerHTML += '<div class="progress-bar"><div class="progress-fill" style="width: ' + 
                                                   message.match(/\\d+/)[0] + '%"></div></div>';
                        }
                    } else {
                        statusBar.innerHTML = message;
                    }
                }
                
                function hideStatus() {
                    setTimeout(() => {
                        statusBar.style.display = 'none';
                    }, 3000);
                }
                
                async function pollStatus(taskId) {
                    const checkInterval = setInterval(async () => {
                        try {
                            const response = await fetch(`/status/${taskId}`);
                            const data = await response.json();
                            
                            if (data.status === 'completed') {
                                clearInterval(checkInterval);
                                showStatus('Video generated successfully!', 'success');
                                
                                // Update video source
                                videoPlayer.src = data.video_url + '?t=' + Date.now();
                                videoPlayer.style.display = 'block';
                                videoPlaceholder.style.display = 'none';
                                videoStatus.textContent = 'Generated at ' + new Date().toLocaleTimeString();
                                
                                generateBtn.disabled = false;
                                generateBtn.textContent = 'Generate Video';
                                hideStatus();
                            } else if (data.status === 'error') {
                                clearInterval(checkInterval);
                                showStatus('Error: ' + data.message, 'error');
                                generateBtn.disabled = false;
                                generateBtn.textContent = 'Generate Video';
                            } else {
                                showStatus(data.message || 'Processing... ' + data.progress + '%', 'processing');
                            }
                        } catch (error) {
                            console.error('Status check error:', error);
                        }
                    }, 2000);
                }
                
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    
                    if (!audioFile.files[0]) {
                        showStatus('Please select an audio file', 'error');
                        return;
                    }
                    
                    const formData = new FormData();
                    formData.append('wav', audioFile.files[0]);
                    formData.append('token', document.getElementById('token').value);
                    
                    generateBtn.disabled = true;
                    generateBtn.textContent = 'Generating...';
                    showStatus('Uploading audio file...', 'processing');
                    
                    try {
                        const response = await fetch('/generate-async', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (!response.ok) {
                            throw new Error('Failed to start generation');
                        }
                        
                        const data = await response.json();
                        showStatus('Processing video... 0%', 'processing');
                        
                        // Start polling for status
                        pollStatus(data.task_id);
                        
                    } catch (error) {
                        console.error('Error:', error);
                        showStatus('Error: ' + error.message, 'error');
                        generateBtn.disabled = false;
                        generateBtn.textContent = 'Generate Video';
                    }
                });
            </script>
        </body>
    </html>
    """)

@app.get("/")
async def root():
    """Redirect to the live update page"""
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
                    <a href="/generate-page" class="btn btn-primary">
                        📄 Classic Mode<br>
                        <small style="font-size: 12px;">(New page for each video)</small>
                    </a>
                    <a href="/live" class="btn btn-secondary">
                        🔄 Live Mode<br>
                        <small style="font-size: 12px;">(Update video in-place)</small>
                    </a>
                </div>
            </div>
        </body>
    </html>
    """)

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
        # Run SyncTalk generation
        cmd = [
            "python3.8", "main.py", "data/May",
            "--workspace", "model/trial_may",
            "-O", "--test", "--test_train",
            "--asr_model", "ave",
            "--portrait",
            "--aud", temp_audio_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Generation failed: {result.stderr}")
        
        # Find and return the generated video
        import glob
        video_files = glob.glob("model/trial_may/results/*_vocal.mp4")
        
        if video_files:
            return FileResponse(video_files[-1], media_type="video/mp4")
        else:
            raise HTTPException(status_code=500, detail="No output video found")
            
    finally:
        # Clean up
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

@app.get("/status/{task_id}")
async def check_status(task_id: str):
    """Check the status of a generation task"""
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return active_tasks[task_id]

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
          // Log the URL we’re trying to play (helps you confirm in the console)
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
    uvicorn.run(app, host="0.0.0.0", port=8080)
