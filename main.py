from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import subprocess
import os
import sys
import re
import time
from datetime import datetime
from supabase import create_client, Client

app = FastAPI(title="CybUrban Rendering Engine (Granular Diagnostics)")

# Load environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else None

class RenderRequest(BaseModel):
    transactionId: str
    renderId: str = None
    city: str
    country: str
    theme: str
    preset: str
    verse: str
    title: str
    distance: int
    amount: float = 0.0

def supabase_callback(status: str, transaction_id: str, result_url: str = None, error: str = None, logs_url: str = None):
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
        "transactionId": transaction_id,
        "status": status,
        "resultPath": result_url,
        "error": error,
        "logsUrl": logs_url,
        "workerId": "railway-worker-engine"
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"Callback failed: {e}")

def run_render_pipeline(req: RenderRequest):
    """Refined background task with granular node updates and log delivery."""
    if not supabase:
        print("✗ Supabase client not initialized. Aborting.")
        return

    full_logs = []
    def log(msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] {msg}"
        print(entry)
        full_logs.append(entry)

    # Telemetry Header
    log("--- SYSTEM TELEMETRY ---")
    log(f"OS: {sys.platform}")
    log(f"Python: {sys.version}")
    log(f"CWD: {os.getcwd()}")
    try:
        import multiprocessing
        log(f"Cores: {multiprocessing.cpu_count()}")
    except: pass
    log("-------------------------")

    last_cli_error = None

    try:
        # STEP 1: Engine Active
        log(f"Initializing engine for transaction {req.transactionId}")
        supabase.table("cyburban_transactions").update({
            "status": "engine_active",
            "full_message": "Rendering environment provisioned. Starting engine..."
        }).eq("id", req.transactionId).execute()
        supabase_callback("engine_active", transaction_id=req.transactionId)

        # STEP 2: Rendering
        log(f"Starting CybUrban CLI core for {req.city}...")
        supabase.table("cyburban_transactions").update({
            "status": "rendering",
            "full_message": "Vulkan Engine active: crunching map pixels and verse typography..."
        }).eq("id", req.transactionId).execute()
        supabase_callback("rendering", transaction_id=req.transactionId)

        target_formats = ["avif"]
        if req.amount >= 200:
            target_formats.append("png")
        
        uploaded_results = {}
        
        for fmt in target_formats:
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
            
            log(f"Running CLI Command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.stdout: full_logs.append(result.stdout)
            if result.stderr: 
                full_logs.append(f"STDERR: {result.stderr}")
                if "Error:" in result.stderr:
                    last_cli_error = result.stderr.strip().split('\n')[-1]

            if result.returncode != 0:
                log(f"⚠ Render error for {fmt}")
                if "Error:" in result.stderr:
                    last_cli_error = result.stderr.strip().split('\n')[-1]
                continue

            match = re.search(r"Wallpaper saved as\s+(.*?\." + fmt + r")", result.stdout)
            if not match:
                match = re.search(r"saved as (.*?posters/.*?\." + fmt + r")", result.stdout)
            
            if match:
                local_path = match.group(1).strip().split('\n')[0].strip()
                if os.path.exists(local_path):
                    filename = f"{req.transactionId}_{os.path.basename(local_path)}"
                    with open(local_path, "rb") as f:
                        supabase.storage.from_("renders").upload(
                            path=filename,
                            file=f,
                            file_options={"content-type": f"image/{fmt}", "x-upsert": "true"}
                        )
                    uploaded_url = supabase.storage.from_("renders").get_public_url(filename)
                    uploaded_results[fmt] = uploaded_url
                    log(f"✓ Uploaded {fmt}: {uploaded_url}")

        if not uploaded_results:
            raise Exception("Pixel Engine failed to produce output assets.")

        # STEP 3: Generated
        log("Assets generated and validated. Preparing delivery...")
        supabase.table("cyburban_transactions").update({
            "status": "generated",
            "full_message": "Asset verification complete. Packaging for delivery..."
        }).eq("id", req.transactionId).execute()
        supabase_callback("generated", transaction_id=req.transactionId)

        # STEP 4: Delivered (Finalize)
        primary_url = uploaded_results.get("png", uploaded_results.get("avif"))
        supabase.table("cyburban_transactions").update({
            "status": "completed",
            "full_message": "Render successfully delivered to your device.",
            "render_url": primary_url
        }).eq("id", req.transactionId).execute()

        supabase_callback("completed", transaction_id=req.transactionId, result_url=primary_url)
        log(f"✓ Automation complete for {req.transactionId}")

        # Cleanup
        for local_file in [f for f in os.listdir("posters") if req.transactionId in f]:
            try:
                os.remove(os.path.join("posters", local_file))
            except: pass

    except Exception as e:
        error_msg = last_cli_error if last_cli_error else str(e)
        log(f"✗ CRITICAL FAILURE: {error_msg}")
        
        # 📂 DIAGNOSTIC LOG DELIVERY
        logs_text = "\n".join(full_logs)
        log_filename = f"error_{req.transactionId}.log"
        logs_url = None
        
        try:
            # Upload logs to 'logs' bucket
            supabase.storage.from_("logs").upload(
                path=log_filename,
                file=logs_text.encode('utf-8'),
                file_options={"content-type": "text/plain", "x-upsert": "true"}
            )
            logs_url = supabase.storage.from_("logs").get_public_url(log_filename)
        except Exception as log_err:
            print(f"Failed to upload troubleshooting logs: {log_err}")

        try:
            # Update fail status with logs
            supabase.table("cyburban_transactions").update({
                "status": "failed",
                "full_message": f"Critical Error: {error_msg}",
                "logs_url": logs_url
            }).eq("id", req.transactionId).execute()

            supabase_callback("failed", transaction_id=req.transactionId, error=error_msg, logs_url=logs_url)
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
