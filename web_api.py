from fastapi.responses import RedirectResponse
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict
import uuid
import threading
import time
import os
import sys
import io
import logging
from main import sync_playlist

app = FastAPI()

def sync_spotify_url(spotify_url):
    """
    Auto-detects URL type and routes to appropriate sync function
    """
    if '/artist/' in spotify_url:
        # Artist sync
        from download_utils import download_missing_artist_tracks_spotdl
        download_dir = "/app/downloads"
        logging.info(f"🎤 Detected artist URL, starting artist sync...")
        download_missing_artist_tracks_spotdl(spotify_url, download_dir)
    elif '/playlist/' in spotify_url:
        # Playlist sync (existing functionality)
        logging.info(f"📋 Detected playlist URL, starting playlist sync...")
        sync_playlist(spotify_url)
    else:
        raise ValueError("Unsupported Spotify URL. Please provide a playlist or artist URL.")

# Redirect root URL to web UI (must be after app is defined)
@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")

# In-memory job store (for demo; use Redis/DB for production)
jobs: Dict[str, Dict] = {}

class SpotifyRequest(BaseModel):
    url: str

@app.post("/submit")
def submit_spotify_sync(req: SpotifyRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "progress": 0, "log": []}
    
    def run_job():
        jobs[job_id]["status"] = "running"
        
        # Custom log handler to capture all logging
        class JobLogHandler(logging.Handler):
            def emit(self, record):
                log_message = self.format(record)
                jobs[job_id]["log"].append(log_message)
        
        # Create log handler and add to root logger
        job_handler = JobLogHandler()
        job_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        job_handler.setFormatter(formatter)
        
        # Get root logger and add our handler
        root_logger = logging.getLogger()
        root_logger.addHandler(job_handler)
        root_logger.setLevel(logging.INFO)
        
        try:
            sync_spotify_url(req.url)
            jobs[job_id]["status"] = "done"
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["log"].append(f"❌ Error: {str(e)}")
        finally:
            # Remove our log handler
            root_logger.removeHandler(job_handler)
    
    background_tasks.add_task(run_job)
    return {"job_id": job_id}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
