import os
# Force matplotlib to use a non-interactive backend
os.environ["MPLBACKEND"] = "Agg"

import io
import logging
import traceback
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import create_map_poster
import create_verse_wallpaper
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Map2Poster API", description="API for generating map posters and verse wallpapers")

# Ensure required directories exist
for d in ["posters", "themes", "fonts", "cache"]:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": traceback.format_exc()},
    )

class PosterRequest(BaseModel):
    city: str
    country: str
    theme: str = "feature_based"
    distance: int = 29000
    format: str = "png"

@app.get("/")
async def root():
    return {
        "message": "Welcome to Map2Poster API",
        "status": "online",
        "endpoints": {
            "/health": "Service health check",
            "/themes": "List available themes",
            "/generate-poster": "Generate a map poster (GET)",
            "/generate-verse-wallpaper": "Generate a verse wallpaper (GET)"
        }
    }

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/themes")
async def list_themes():
    try:
        themes = create_map_poster.get_available_themes()
        return {"themes": themes}
    except Exception as e:
        logger.error(f"Error listing themes: {e}")
        raise

@app.get("/generate-poster")
async def generate_poster(
    city: str,
    country: str,
    theme: str = "feature_based",
    distance: int = 29000,
    format: str = "png"
):
    logger.info(f"Generating poster for {city}, {country} with theme {theme}")
    # Load theme
    create_map_poster.THEME = create_map_poster.load_theme(theme)
    
    # Get coordinates
    coords = create_map_poster.get_coordinates(city, country)
    
    # Generate filename
    output_file = create_map_poster.generate_output_filename(city, theme, format)
    
    # Create poster
    create_map_poster.create_poster(city, country, coords, distance, output_file, format)
    
    if os.path.exists(output_file):
        return FileResponse(output_file, media_type=f"image/{format}")
    else:
        raise HTTPException(status_code=500, detail="Generated file not found on disk")

@app.get("/generate-verse-wallpaper")
async def generate_verse_wallpaper(
    city: str,
    country: str,
    verse_text: str = "",
    verse_title: str = "",
    theme_name: str = "noir",
    preset: str = "mobile",
    output_format: str = "png",
    verse_position: str = "center",
    clear_size: Optional[str] = None,
    watermark: bool = True,
    quality: int = 90,
    dpi: int = 100
):
    logger.info(f"Generating verse wallpaper for {city}, {country} with theme {theme_name}")
    logger.info(f"Params: preset={preset}, format={output_format}, watermark={watermark}, quality={quality}, dpi={dpi}")
    
    # Get coordinates
    coords = create_verse_wallpaper.get_coordinates(city, country)
    
    # Get distance from theme if possible, else default
    temp_theme = create_map_poster.load_theme(theme_name)
    dist = temp_theme.get('distance', 10000)
    
    # Generate wallpaper
    output_path = create_verse_wallpaper.create_verse_wallpaper(
        city=city,
        country=country,
        point=coords,
        dist=dist,
        verse_text=verse_text,
        verse_title=verse_title,
        theme_name=theme_name,
        preset=preset,
        output_format=output_format,
        verse_position_name=verse_position,
        clear_size=clear_size,
        watermark=watermark,
        quality=quality,
        dpi=dpi
    )
    
    if output_path and os.path.exists(output_path):
        media_type = f"image/{output_format}"
        if output_format == "avif":
            media_type = "image/avif"
        return FileResponse(output_path, media_type=media_type)
    else:
        raise HTTPException(status_code=500, detail="Generated wallpaper not found on disk")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
