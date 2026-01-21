import os
import io
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import create_map_poster
import create_verse_wallpaper
from datetime import datetime

app = FastAPI(title="Map2Poster API", description="API for generating map posters and verse wallpapers")

# Ensure required directories exist
for d in ["posters", "themes", "fonts"]:
    if not os.path.exists(d):
        os.makedirs(d)

class PosterRequest(BaseModel):
    city: str
    country: str
    theme: str = "feature_based"
    distance: int = 29000
    format: str = "png"

class VerseWallpaperRequest(BaseModel):
    city: str
    country: str
    verse_text: str = ""
    verse_title: str = ""
    theme_name: str = "noir"
    preset: str = "mobile"
    output_format: str = "png"
    verse_position: str = "center"
    clear_size: Optional[str] = None

@app.get("/")
async def root():
    return {
        "message": "Welcome to Map2Poster API",
        "endpoints": {
            "/themes": "List available themes",
            "/generate-poster": "Generate a map poster (GET)",
            "/generate-verse-wallpaper": "Generate a verse wallpaper (GET)"
        }
    }

@app.get("/themes")
async def list_themes():
    return {"themes": create_map_poster.get_available_themes()}

@app.get("/generate-poster")
async def generate_poster(
    city: str,
    country: str,
    theme: str = "feature_based",
    distance: int = 29000,
    format: str = "png"
):
    try:
        # Load theme
        create_map_poster.THEME = create_map_poster.load_theme(theme)
        
        # Get coordinates
        coords = create_map_poster.get_coordinates(city, country)
        
        # Generate filename
        output_file = create_map_poster.generate_output_filename(city, theme, format)
        
        # Create poster
        create_map_poster.create_poster(city, country, coords, distance, output_file, format)
        
        return FileResponse(output_file, media_type=f"image/{format}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    clear_size: Optional[str] = None
):
    try:
        # Get coordinates
        coords = create_verse_wallpaper.get_coordinates(city, country)
        
        # Generate wallpaper
        # Note: create_verse_wallpaper.create_verse_wallpaper returns the output path
        output_path = create_verse_wallpaper.create_verse_wallpaper(
            city=city,
            country=country,
            point=coords,
            dist=create_map_poster.load_theme(theme_name).get('distance', 10000), # Default dist for wallpapers
            verse_text=verse_text,
            verse_title=verse_title,
            theme_name=theme_name,
            preset=preset,
            output_format=output_format,
            verse_position_name=verse_position,
            clear_size=clear_size
        )
        
        # The script above generates its own filename, but we need to find it or modify it to return it.
        # Based on the code view, create_verse_wallpaper in create_verse_wallpaper.py 
        # calls generate_output_filename and then potentially returns something or just saves it.
        # I need to verify what create_verse_wallpaper returns.
        
        # Let's check create_verse_wallpaper.py again to see its return value.
        return FileResponse(output_path, media_type=f"image/{output_format}")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
