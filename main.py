from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import subprocess
import os
import requests
import sys
import re

app = FastAPI(title="CybUrban Rendering Engine (CLI Wrapper)")

# Load environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

class RenderRequest(BaseModel):
    transactionId: str
    city: str
    country: str
    theme: str
    preset: str
    verse: str
    title: str
    distance: int

def run_render_pipeline(req: RenderRequest):
    """Background task to run the CLI tool and sync to Supabase."""
    db_url = f"{SUPABASE_URL}/rest/v1/cyburban_transactions?id=eq.{req.transactionId}"
    db_headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    try:
        # 1. Build CLI Arguments
        # Note: We use the EXACT flags from the original script
        cmd = [
            sys.executable, "create_verse_wallpaper.py",
            "-c", req.city,
            "-C", req.country,
            "-t", req.theme,
            "-p", req.preset,
            "-d", str(req.distance),
            "--verse", req.verse,
            "--title", req.title,
            "-f", "png" # Force PNG for consistent processing
        ]

        print(f"Running CLI: {' '.join(cmd)}")
        
        # 2. Execute Script
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"CLI Error: {result.stderr}")

        # 3. Find the output filename from stdout
        # Looking for line: "✓ Done! Wallpaper saved as <path>"
        match = re.search(r"Wallpaper saved as\s+(.*\.png)", result.stdout)
        if not match:
            raise Exception("Could not find output filename in script output")
        
        local_path = match.group(1).strip()
        print(f"Detected local file: {local_path}")

        if not os.path.exists(local_path):
            raise Exception(f"File {local_path} not found on disk")

        # 4. Upload to Supabase Storage
        filename = f"{req.transactionId}.png"
        storage_url = f"{SUPABASE_URL}/storage/v1/object/verse_backgrounds/{filename}"
        
        with open(local_path, "rb") as f:
            file_data = f.read()

        storage_headers = {
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "image/png"
        }
        
        # Try POST (new) then PUT (overwrite)
        resp = requests.post(storage_url, headers=storage_headers, data=file_data)
        if resp.status_code == 400:
            resp = requests.put(storage_url, headers=storage_headers, data=file_data)

        if resp.status_code not in [200, 201]:
            raise Exception(f"Storage upload failed: {resp.text}")

        render_url = f"{SUPABASE_URL}/storage/v1/object/public/verse_backgrounds/{filename}"

        # 5. Finalize DB
        requests.patch(db_url, headers=db_headers, json={
            "status": "completed",
            "full_message": f"Render Delivered: {render_url}"
        })

        # 6. Cleanup local file
        if os.path.exists(local_path):
            os.remove(local_path)
            print(f"Cleaned up local file: {local_path}")

        print(f"✓ Automation complete for {req.transactionId}")

    except Exception as e:
        print(f"✗ Automation failed: {e}")
        try:
            requests.patch(db_url, headers=db_headers, json={"status": "failed"})
        except: pass

@app.post("/render")
async def trigger_render(req: RenderRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_render_pipeline, req)
    return {"status": "accepted", "message": "Job queued", "transactionId": req.transactionId}

@app.get("/health")
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
