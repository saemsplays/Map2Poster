from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import subprocess
import os
import sys
import re
from supabase import create_client, Client

app = FastAPI(title="CybUrban Rendering Engine (Supabase Integrated)")

# Load environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("WARNING: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set!")

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else None

class RenderRequest(BaseModel):
    transactionId: str
    renderId: str = None  # Optional but recommended for full tracking
    city: str
    country: str
    theme: str
    preset: str
    verse: str
    title: str
    distance: int
    amount: float = 0.0

def supabase_callback(status: str, render_id: str = None, transaction_id: str = None, result_url: str = None, error: str = None):
    """Notify Supabase Edge Function to handle notifications and complex logic."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return
    
    import requests
    url = f"{SUPABASE_URL}/functions/v1/render-complete"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "renderId": render_id,
        "transactionId": transaction_id,
        "status": status,
        "resultPath": result_url,
        "error": error,
        "workerId": "railway-worker-engine"
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"Callback failed: {e}")

def run_render_pipeline(req: RenderRequest):
    """Background task to run the CLI tool and sync to Supabase."""
    if not supabase:
        print("✗ Supabase client not initialized. Aborting.")
        return

    try:
        # 1. Update status and trigger callback
        supabase.table("cyburban_transactions").update({
            "status": "processing",
            "full_message": "Render engine started..."
        }).eq("id", req.transactionId).execute()

        # Trigger Edge Function for notifications
        supabase_callback("processing", render_id=req.renderId, transaction_id=req.transactionId)

        supabase.table("render_jobs_audit").insert({
            "transaction_id": req.transactionId,
            "render_id": req.renderId,
            "event_type": "render_started",
            "details": {"engine": "CybUrban-Python-CLI"}
        }).execute()

        # 2. Determine formats based on amount (Tiers)
        # Standard (50): AVIF
        # HD (200): PNG + AVIF
        # Max (1000): PNG + AVIF
        target_formats = ["avif"]
        if req.amount >= 200:
            target_formats.append("png")
        
        uploaded_results = {}
        
        for fmt in target_formats:
            # 3. Build CLI Arguments
            cmd = [
                sys.executable, "create_verse_wallpaper.py",
                "-c", req.city,
                "-C", req.country,
                "-t", req.theme,
                "-p", req.preset,
                "-d", str(req.distance),
                "--verse", req.verse,
                "--title", req.title,
                "-f", fmt
            ]
            
            print(f"Running CLI for format {fmt}: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"⚠ Render error for {fmt}: {result.stderr}")
                continue # Try next format if one fails

            # 4. Find the output filename from stdout
            match = re.search(r"Wallpaper saved as\s+(.*?\." + fmt + r")", result.stdout)
            if not match:
                # Fallback check
                match = re.search(r"saved as (.*?posters/.*?\." + fmt + r")", result.stdout)
                if not match:
                    print(f"⚠ Could not find output filename for {fmt}")
                    continue
            
            local_path = match.group(1).strip()
            # Clean up potential terminal formatting or spaces
            local_path = local_path.split('\n')[0].strip()
            
            if not os.path.exists(local_path):
                print(f"⚠ File {local_path} not found on disk")
                continue

            # 5. Upload to Supabase Storage
            # Use original filename to preserve metadata/format info
            filename = os.path.basename(local_path)
            
            with open(local_path, "rb") as f:
                supabase.storage.from_("renders").upload(
                    path=filename,
                    file=f,
                    file_options={"content-type": f"image/{fmt}", "x-upsert": "true"}
                )

            uploaded_url = supabase.storage.from_("renders").get_public_url(filename)
            uploaded_results[fmt] = uploaded_url
            print(f"✓ Uploaded {fmt}: {uploaded_url}")

        if not uploaded_results:
            raise Exception("No renders were successfully generated or uploaded.")

        # 6. Finalize DB and trigger completion callback
        # Use PNG if available as primary, otherwise AVIF
        primary_url = uploaded_results.get("png", uploaded_results.get("avif"))
        
        supabase.table("cyburban_transactions").update({
            "status": "completed",
            "full_message": f"Render Delivered: {', '.join(uploaded_results.keys()).upper()}",
            "render_url": primary_url
        }).eq("id", req.transactionId).execute()

        supabase_callback("completed", render_id=req.renderId, transaction_id=req.transactionId, result_url=primary_url)

        supabase.table("render_jobs_audit").insert({
            "transaction_id": req.transactionId,
            "render_id": req.renderId,
            "event_type": "render_completed",
            "details": {"urls": uploaded_results}
        }).execute()

        # 7. Cleanup local files
        for local_file in [f for f in os.listdir("posters") if req.transactionId in f or any(res in f for res in uploaded_results.keys())]:
            try:
                path = os.path.join("posters", local_file)
                if os.path.isfile(path):
                    os.remove(path)
                    print(f"Cleaned up local file: {path}")
            except Exception as e:
                print(f"Error cleaning up {local_file}: {e}")

        print(f"✓ Automation complete for {req.transactionId}")

    except Exception as e:
        error_msg = str(e)
        print(f"✗ Automation failed: {error_msg}")
        try:
            # Using Supabase client for error status
            supabase.table("cyburban_transactions").update({
                "status": "failed",
                "full_message": f"Error: {error_msg}"
            }).eq("id", req.transactionId).execute()

            supabase_callback("failed", render_id=req.renderId, transaction_id=req.transactionId, error=error_msg)

            supabase.table("render_jobs_audit").insert({
                "transaction_id": req.transactionId,
                "render_id": req.renderId,
                "event_type": "render_failed",
                "details": {"error": error_msg}
            }).execute()
        except Exception as inner:
            print(f"Error updating fail status: {inner}")

@app.post("/render")
async def trigger_render(req: RenderRequest, background_tasks: BackgroundTasks):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase client not configured")
    background_tasks.add_task(run_render_pipeline, req)
    return {"status": "accepted", "message": "Job queued", "transactionId": req.transactionId}

@app.get("/health")
def health():
    return {"status": "healthy", "supabase_connected": supabase is not None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
