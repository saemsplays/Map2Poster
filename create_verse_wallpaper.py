"""
Verse Wallpaper Generator for NOD App
=====================================
Creates map-based wallpapers with integrated verse text, clearing zones,
and NOD branding for mobile and desktop devices.

Features:
- Multiple resolution presets (mobile, mobile_hd, desktop, desktop_hd, stories)
- Four clearing sizes (none, thin, mid, large) based on verse length
- Theme-based clearing color that blends with map background
- SVG logo integration with theme text color matching
- Verse position variants for desktop (center, left, right, above, below)
- Feathered alpha masks with Gaussian blending
"""

import osmnx as ox
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import matplotlib.colors as mcolors
import numpy as np
from scipy.ndimage import gaussian_filter
from geopy.geocoders import Nominatim
from tqdm import tqdm
import time
import json
import os
from datetime import datetime
import argparse
from PIL import Image
import io
import textwrap
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# No external SVG libraries needed - using PNG logos with PIL color tinting

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

THEMES_DIR = "themes"
FONTS_DIR = "fonts"
POSTERS_DIR = "posters"
ASSETS_DIR = "."  # Logo files are in root

# Resolution presets (width, height)
PRESETS = {
    'mobile': (1080, 1920),
    'mobile_hd': (1440, 2560),
    'desktop': (1920, 1080),
    'desktop_hd': (2560, 1440),
    'stories': (1080, 1920),
    # High-DPI / High-Quality Presets
    'mobile_max': (1800, 2400),
    'desktop_max': (2400, 3200),
    'ultra_hd': (3600, 4800),
}

# Clearing size parameters (fraction of canvas height)
CLEARING_CONFIG = {
    'none': {
        'verse_height_fraction': 0.0,
        'title_height_fraction': 0.0,
        'enabled': False,
    },
    'thin': {
        'verse_height_fraction': 0.15,
        'title_height_fraction': 0.08,
        'enabled': True,
    },
    'mid': {
        'verse_height_fraction': 0.25,
        'title_height_fraction': 0.10,
        'enabled': True,
    },
    'large': {
        'verse_height_fraction': 0.40,
        'title_height_fraction': 0.12,
        'enabled': True,
    },
}

# Clearing parameters
TITLE_WIDTH_FRACTION = 0.5
TITLE_GAP_FRACTION = 0.02
VERSE_Y_CENTER = 0.58  # Slightly above midpoint
MAX_ALPHA = 0.92
FEATHER_SIGMA_FRACTION = 0.35

# Verse position presets for desktop (horizontal x_center, vertical y_center)
VERSE_POSITIONS = {
    'center': {'x_center': 0.5, 'y_center': 0.58},
    'left': {'x_center': 0.25, 'y_center': 0.55},
    'right': {'x_center': 0.75, 'y_center': 0.55},
    'above': {'x_center': 0.5, 'y_center': 0.70},
    'below': {'x_center': 0.5, 'y_center': 0.40},
}

# Network hardening for Overpass API
ox.settings.requests_timeout = 300
ox.settings.timeout = 300
ox.settings.overpass_rate_limit = False  # kumi.systems handles its own rate limiting
ox.settings.overpass_endpoint = 'https://overpass.kumi.systems/api/interpreter'
ox.settings.overpass_url = 'https://overpass.kumi.systems/api/interpreter'
ox.settings.log_console = True  # Enable logging to see what's happening

# Configure persistent session with retries for requests
session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
session.mount('https://', HTTPAdapter(max_retries=retries))
ox.settings.requests_kwargs = {'verify': True}

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def load_fonts():
    """Load Roboto fonts from the fonts directory."""
    fonts = {
        'bold': os.path.join(FONTS_DIR, 'Roboto-Bold.ttf'),
        'regular': os.path.join(FONTS_DIR, 'Roboto-Regular.ttf'),
        'light': os.path.join(FONTS_DIR, 'Roboto-Light.ttf')
    }
    for weight, path in fonts.items():
        if not os.path.exists(path):
            print(f"⚠ Font not found: {path}")
            return None
    return fonts


FONTS = load_fonts()


def get_available_themes():
    """Scans the themes directory and returns a list of available theme names."""
    if not os.path.exists(THEMES_DIR):
        os.makedirs(THEMES_DIR)
        return []
    themes = []
    for file in sorted(os.listdir(THEMES_DIR)):
        if file.endswith('.json'):
            theme_name = file[:-5]
            themes.append(theme_name)
    return themes


def load_theme(theme_name="feature_based"):
    """Load theme from JSON file in themes directory."""
    theme_file = os.path.join(THEMES_DIR, f"{theme_name}.json")
    if not os.path.exists(theme_file):
        print(f"⚠ Theme file '{theme_file}' not found. Using default.")
        return {
            "name": "Default",
            "bg": "#FFFFFF",
            "text": "#000000",
            "gradient_color": "#FFFFFF",
            "water": "#C0C0C0",
            "parks": "#F0F0F0",
            "road_motorway": "#0A0A0A",
            "road_primary": "#1A1A1A",
            "road_secondary": "#2A2A2A",
            "road_tertiary": "#3A3A3A",
            "road_residential": "#4A4A4A",
            "road_default": "#3A3A3A"
        }
    with open(theme_file, 'r') as f:
        theme = json.load(f)
        print(f"✓ Loaded theme: {theme.get('name', theme_name)}")
        return theme


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple (0-255)."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    """Convert RGB tuple (0-255) to hex color."""
    return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def compute_relative_luminance(hex_color):
    """
    Compute relative luminance of a color.
    Uses sRGB to linear conversion then Y = 0.2126*R + 0.7152*G + 0.0722*B
    Returns value between 0 (darkest) and 1 (brightest).
    """
    r, g, b = hex_to_rgb(hex_color)
    
    def linearize(c):
        c = c / 255.0
        if c <= 0.03928:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4
    
    r_lin = linearize(r)
    g_lin = linearize(g)
    b_lin = linearize(b)
    
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def compute_verse_clear_size(verse_length):
    """
    Determine clearing size category based on verse character count.
    Returns: 'none', 'thin', 'mid', or 'large'
    """
    if verse_length == 0:
        return 'none'
    elif verse_length <= 60:
        return 'thin'
    elif verse_length <= 180:
        return 'mid'
    else:
        return 'large'


def get_logo_png_path(theme):
    """
    Determine which logo PNG to use based on theme background luminance.
    - Dark background → use NOD-LOGO-dark.png (white logo base)
    - Light background → use NOD-LOGO-light.png (black logo base)
    """
    bg_luminance = compute_relative_luminance(theme['bg'])
    if bg_luminance < 0.5:
        return os.path.join(ASSETS_DIR, 'NOD-LOGO-dark.png')
    else:
        return os.path.join(ASSETS_DIR, 'NOD-LOGO-light.png')


def render_logo_with_color(theme, target_height):
    """
    Render logo with theme's text color, maintaining aspect ratio.
    Uses PNG base with PIL color tinting.
    Returns PIL Image with transparency.
    """
    logo_path = get_logo_png_path(theme)
    target_color = hex_to_rgb(theme['text'])
    
    if not os.path.exists(logo_path):
        print(f"⚠ Logo PNG not found: {logo_path}")
        return None
    
    try:
        # Load the base logo
        logo = Image.open(logo_path).convert('RGBA')
        
        # Calculate width to maintain aspect ratio
        w, h = logo.size
        aspect = w / h
        target_width = int(target_height * aspect)
        
        # Resize to target size
        logo = logo.resize((target_width, target_height), Image.LANCZOS)
        
        # Get the alpha channel
        r, g, b, a = logo.split()
        
        # Create a new image with the target color
        color_layer = Image.new('RGBA', logo.size, target_color + (255,))
        
        # Apply the original alpha mask to the colored layer
        color_layer.putalpha(a)
        
        return color_layer
    except Exception as e:
        print(f"⚠ Error rendering logo: {e}")
        return None


def generate_output_filename(city, theme_name, preset, output_format):
    """Generate unique output filename."""
    if not os.path.exists(POSTERS_DIR):
        os.makedirs(POSTERS_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    city_slug = city.lower().replace(' ', '_')
    ext = output_format.lower()
    filename = f"verse_{city_slug}_{theme_name}_{preset}_{timestamp}.{ext}"
    return os.path.join(POSTERS_DIR, filename)


def get_coordinates(city, country):
    """Fetches coordinates for a given city and country using geopy with retries."""
    print("Looking up coordinates...")
    geolocator = Nominatim(user_agent="verse_wallpaper_generator")
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            # Respect Nominatim's usage policy with a sleep
            time.sleep(1.5)
            location = geolocator.geocode(f"{city}, {country}")
            if location:
                print(f"✓ Found: {location.address}")
                print(f"✓ Coordinates: {location.latitude}, {location.longitude}")
                return (location.latitude, location.longitude)
            else:
                raise ValueError(f"Could not find coordinates for {city}, {country}")
        except Exception as e:
            if attempt < max_attempts - 1:
                wait_time = (attempt + 1) * 3
                print(f"  ⚠ Geocoding attempt {attempt+1} failed ({e}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e


def shift_map_center(lat, lon, verse_y_center, dist_m):
    """
    Shift the map center so that city features appear below the clearing zone.
    Returns new (lat, lon) tuple.
    """
    desired_visual_offset = verse_y_center - 0.5
    lat_shift_meters = -desired_visual_offset * (dist_m * 2) * 0.8
    lat_shift_degrees = lat_shift_meters / 111320.0
    new_lat = lat + lat_shift_degrees
    return (new_lat, lon)


# =============================================================================
# CLEARING MASK GENERATION
# =============================================================================

def create_verse_clearing_mask(W_px, H_px, clear_config, verse_position, theme):
    """
    Creates an RGBA mask for the verse clearing area with Gaussian blur.
    Now supports restricted width proportional to text coverage.
    
    Args:
        W_px, H_px: Canvas dimensions
        clear_config: Clearing size configuration (includes verse_width_fraction)
        verse_position: Position dict with x_center and y_center
        theme: Theme dictionary
        
    Returns:
        RGBA numpy array with clearing mask
    """
    if not clear_config['enabled']:
        return None
    
    # Use theme background color for clearing (blends naturally)
    clear_color_rgb = hex_to_rgb(theme['bg'])
    
    # Create coordinate arrays
    y_coords = np.linspace(0, 1, H_px)
    x_coords = np.linspace(0, 1, W_px)
    
    # Main clearing parameters
    verse_height_frac = clear_config['verse_height_fraction']
    verse_width_frac = clear_config.get('verse_width_fraction', 0.8)
    title_height_frac = clear_config.get('title_height_fraction', 0.08)
    
    y_center = verse_position['y_center']
    x_center = verse_position['x_center']
    
    h_main = verse_height_frac / 2
    sigma_main = FEATHER_SIGMA_FRACTION * verse_height_frac
    
    # Horizontal buffer for clearing (fraction of width)
    x_buffer = 0.12 # Coverage buffer
    
    # Horizontal extents for main clearing based on alignment
    if x_center > 0.9: # Right aligned
        main_x_left = 1.0 - (verse_width_frac + x_buffer)
        main_x_right = 1.0
    elif x_center < 0.1: # Left aligned
        main_x_left = 0.0
        main_x_right = verse_width_frac + x_buffer
    else: # Center aligned
        main_x_left = x_center - (verse_width_frac + x_buffer) / 2
        main_x_right = x_center + (verse_width_frac + x_buffer) / 2
    
    # FEATHER_SIGMA_FRACTION for horizontal should be similar to vertical or slightly smaller
    sigma_x = FEATHER_SIGMA_FRACTION * 0.15 

    # Create main clearing mask (2D Gaussian-ish)
    main_alpha = np.zeros((H_px, W_px), dtype=np.float32)
    
    for i, y in enumerate(y_coords):
        d_y = (y - y_center) / h_main if h_main > 0 else 0
        alpha_y = np.exp(-0.5 * (d_y / sigma_main) ** 2) if sigma_main > 0 else 0
        
        for j, x in enumerate(x_coords):
            # Horizontal falloff for main clearing
            if x < main_x_left:
                d_x = (main_x_left - x) / sigma_x
                alpha_x = np.exp(-0.5 * d_x ** 2)
            elif x > main_x_right:
                d_x = (x - main_x_right) / sigma_x
                alpha_x = np.exp(-0.5 * d_x ** 2)
            else:
                alpha_x = 1.0
            
            main_alpha[i, j] = MAX_ALPHA * alpha_y * alpha_x
    
    # Create title clearing mask (dynamic offset)
    title_alpha = np.zeros((H_px, W_px), dtype=np.float32)
    
    title_y_offset = clear_config.get('title_y_offset', h_main + TITLE_GAP_FRACTION + title_height_frac / 2)
    title_y_center = y_center + title_y_offset
    h_title = title_height_frac / 2
    sigma_title = FEATHER_SIGMA_FRACTION * title_height_frac
    
    # Align title clearing with text alignment
    title_width = TITLE_WIDTH_FRACTION
    
    if x_center > 0.9: # Right aligned
        title_x_left = 1.0 - title_width
        title_x_right = 1.0
    elif x_center < 0.1: # Left aligned
        title_x_left = 0.0
        title_x_right = title_width
    else: # Center aligned
        title_x_left = x_center - title_width / 2
        title_x_right = x_center + title_width / 2
    
    for i, y in enumerate(y_coords):
        d_y = (y - title_y_center) / h_title if h_title > 0 else 0
        alpha_y = np.exp(-0.5 * (d_y / sigma_title) ** 2) if sigma_title > 0 else 0
        
        for j, x in enumerate(x_coords):
            # Horizontal feathering for title
            if x < title_x_left:
                d_x = (title_x_left - x) / (sigma_title * 0.5)
                alpha_x = np.exp(-0.5 * d_x ** 2)
            elif x > title_x_right:
                d_x = (x - title_x_right) / (sigma_title * 0.5)
                alpha_x = np.exp(-0.5 * d_x ** 2)
            else:
                alpha_x = 1.0
            
            title_alpha[i, j] = MAX_ALPHA * 0.85 * alpha_y * alpha_x
    
    # Combine masks (take max)
    combined_alpha = np.maximum(main_alpha, title_alpha)
    
    # Apply Gaussian blur for smoother feathering
    blur_sigma = max(H_px, W_px) * 0.008
    combined_alpha = gaussian_filter(combined_alpha, sigma=blur_sigma)
    combined_alpha = np.clip(combined_alpha, 0, MAX_ALPHA)
    
    # Create RGBA image
    mask_rgba = np.zeros((H_px, W_px, 4), dtype=np.uint8)
    mask_rgba[:, :, 0] = clear_color_rgb[0]
    mask_rgba[:, :, 1] = clear_color_rgb[1]
    mask_rgba[:, :, 2] = clear_color_rgb[2]
    mask_rgba[:, :, 3] = (combined_alpha * 255).astype(np.uint8)
    
    return mask_rgba


# =============================================================================
# ROAD RENDERING FUNCTIONS
# =============================================================================

def get_edge_colors_by_type(G, theme):
    """Assigns colors to edges based on road type hierarchy."""
    edge_colors = []
    for u, v, data in G.edges(data=True):
        highway = data.get('highway', 'unclassified')
        if isinstance(highway, list):
            highway = highway[0] if highway else 'unclassified'
        
        if highway in ['motorway', 'motorway_link']:
            color = theme['road_motorway']
        elif highway in ['trunk', 'trunk_link', 'primary', 'primary_link']:
            color = theme['road_primary']
        elif highway in ['secondary', 'secondary_link']:
            color = theme['road_secondary']
        elif highway in ['tertiary', 'tertiary_link']:
            color = theme['road_tertiary']
        elif highway in ['residential', 'living_street', 'unclassified']:
            color = theme['road_residential']
        else:
            color = theme['road_default']
        
        edge_colors.append(color)
    return edge_colors


def get_edge_widths_by_type(G, scale_factor=1.0):
    """Assigns line widths to edges based on road type."""
    edge_widths = []
    for u, v, data in G.edges(data=True):
        highway = data.get('highway', 'unclassified')
        if isinstance(highway, list):
            highway = highway[0] if highway else 'unclassified'
        
        if highway in ['motorway', 'motorway_link']:
            width = 1.2 * scale_factor
        elif highway in ['trunk', 'trunk_link', 'primary', 'primary_link']:
            width = 1.0 * scale_factor
        elif highway in ['secondary', 'secondary_link']:
            width = 0.8 * scale_factor
        elif highway in ['tertiary', 'tertiary_link']:
            width = 0.6 * scale_factor
        else:
            width = 0.4 * scale_factor
        
        edge_widths.append(width)
    return edge_widths


# =============================================================================
# GRADIENT FUNCTIONS
# =============================================================================

def create_gradient_fade(ax, color, location='bottom', zorder=10, height_fraction=0.25):
    """Creates a fade effect at the top or bottom of the map."""
    vals = np.linspace(0, 1, 256).reshape(-1, 1)
    gradient = np.hstack((vals, vals))
    
    rgb = mcolors.to_rgb(color)
    my_colors = np.zeros((256, 4))
    my_colors[:, 0] = rgb[0]
    my_colors[:, 1] = rgb[1]
    my_colors[:, 2] = rgb[2]
    
    if location == 'bottom':
        my_colors[:, 3] = np.linspace(1, 0, 256)
        extent_y_start = 0
        extent_y_end = height_fraction
    else:
        my_colors[:, 3] = np.linspace(0, 1, 256)
        extent_y_start = 1 - height_fraction
        extent_y_end = 1.0
    
    custom_cmap = mcolors.ListedColormap(my_colors)
    
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    y_range = ylim[1] - ylim[0]
    
    y_bottom = ylim[0] + y_range * extent_y_start
    y_top = ylim[0] + y_range * extent_y_end
    
    ax.imshow(gradient, extent=[xlim[0], xlim[1], y_bottom, y_top],
              aspect='auto', cmap=custom_cmap, zorder=zorder, origin='lower')


# =============================================================================
# MAIN WALLPAPER GENERATION
# =============================================================================

def create_verse_wallpaper(
    city, country, point, dist,
    verse_text="", verse_title="",
    theme_name="noir", preset="mobile",
    output_format="png", verse_position_name="center",
    clear_size=None
):
    """
    Generate a verse wallpaper with map background.
    
    Args:
        city, country: Location names
        point: (lat, lon) tuple
        dist: Map radius in meters
        verse_text: The verse content
        verse_title: The verse reference (e.g., "Psalm 90:12")
        theme_name: Name of theme to use
        preset: Resolution preset name
        output_format: png, webp, or avif
        verse_position_name: center/left/right/above/below
        clear_size: none/thin/mid/large (auto-computed if None)
    
    Returns:
        Path to generated file
    """
    # Load theme
    theme = load_theme(theme_name)
    
    # Get dimensions
    W_px, H_px = PRESETS.get(preset, PRESETS['mobile'])
    is_landscape = W_px > H_px
    
    # Compute scale factor for fonts and widths
    base_height = 1920
    scale_factor = H_px / base_height
    
    # Determine clearing size
    if clear_size is None:
        verse_length = len(verse_text)
        clear_size = compute_verse_clear_size(verse_length)
    
    print(f"✓ Clearing size: {clear_size} (verse length: {len(verse_text)} chars)")
    
    clear_config = CLEARING_CONFIG[clear_size]
    
    # Get verse position
    if is_landscape and verse_position_name in VERSE_POSITIONS:
        verse_position = VERSE_POSITIONS[verse_position_name]
    else:
        verse_position = VERSE_POSITIONS['center']
    
    # Shift map center for better composition
    if clear_config['enabled']:
        shifted_point = shift_map_center(
            point[0], point[1],
            verse_position['y_center'],
            dist
        )
    else:
        shifted_point = point
    
    print(f"\nGenerating verse wallpaper for {city}, {country}...")
    print(f"  Preset: {preset} ({W_px}x{H_px})")
    print(f"  Theme: {theme.get('name', theme_name)}")
    
    # Compute figure size for matplotlib (at 100 DPI base)
    dpi = 100
    fig_width = W_px / dpi
    fig_height = H_px / dpi
    
    # Fetch map data with hardening
    with tqdm(total=3, desc="Fetching map data", unit="step") as pbar:
        # Step 1: Download street network
        pbar.set_description("Downloading street network")
        
        # Determine density-based fetching strategy
        # For very large distances or known dense areas, we might need drive network
        fetch_network_type = 'all'
        if dist > 10000 and city.lower() in ['nairobi', 'tokyo', 'mumbai', 'delhi']:
            print(f"\n  ! Dense area detected: Using 'drive' network type for stability.")
            fetch_network_type = 'drive'
        
        # Final retry loop for the graph fetching
        max_attempts = 3
        G = None
        for attempt in range(max_attempts):
            try:
                G = ox.graph_from_point(
                    shifted_point, 
                    dist=dist, 
                    dist_type='bbox', 
                    network_type=fetch_network_type,
                    simplify=True
                )
                if G: break
            except Exception as e:
                if attempt < max_attempts - 1:
                    wait_time = (attempt + 1) * 5
                    print(f"\n  ⚠ API attempt {attempt+1} failed. Retrying in {wait_time}s... ({e})")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Failed to download map data after {max_attempts} attempts: {e}")
        
        pbar.update(1)
        
        # Step 2: Download water features
        pbar.set_description("Downloading water features")
        try:
            water = ox.features_from_point(shifted_point, tags={'natural': 'water', 'waterway': 'riverbank'}, dist=dist)
        except Exception as e:
            print(f"\n  ⚠ Water download failed (skipped): {e}")
            water = None
        pbar.update(1)
        
        # Step 3: Download parks/green spaces
        pbar.set_description("Downloading parks/green spaces")
        try:
            parks = ox.features_from_point(shifted_point, tags={'leisure': 'park', 'landuse': 'grass'}, dist=dist)
        except Exception as e:
            print(f"\n  ⚠ Parks download failed (skipped): {e}")
            parks = None
        pbar.update(1)
    
    print("✓ All data downloaded!")
    
    # Create figure
    print("Rendering map...")
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor=theme['bg'])
    ax.set_facecolor(theme['bg'])
    ax.set_position([0, 0, 1, 1])
    
    # Plot water
    if water is not None and not water.empty:
        water_polys = water[water.geometry.type.isin(['Polygon', 'MultiPolygon'])]
        if not water_polys.empty:
            water_polys.plot(ax=ax, facecolor=theme['water'], edgecolor='none', zorder=1)
    
    # Plot parks
    if parks is not None and not parks.empty:
        parks_polys = parks[parks.geometry.type.isin(['Polygon', 'MultiPolygon'])]
        if not parks_polys.empty:
            parks_polys.plot(ax=ax, facecolor=theme['parks'], edgecolor='none', zorder=2)
    
    # Plot roads
    print("Applying road hierarchy colors...")
    edge_colors = get_edge_colors_by_type(G, theme)
    edge_widths = get_edge_widths_by_type(G, scale_factor)
    
    ox.plot_graph(
        G, ax=ax, bgcolor=theme['bg'],
        node_size=0,
        edge_color=edge_colors,
        edge_linewidth=edge_widths,
        show=False, close=False
    )
    
    # Create and apply clearing mask
    if clear_config['enabled']:
        print("Creating verse clearing...")
        mask_rgba = create_verse_clearing_mask(W_px, H_px, clear_config, verse_position, theme)
        if mask_rgba is not None:
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            ax.imshow(mask_rgba, extent=[xlim[0], xlim[1], ylim[0], ylim[1]],
                      aspect='auto', zorder=8, origin='lower')
    
    # ==========================================================================
    # TYPOGRAPHY AND BRANDING SETUP
    # ==========================================================================
    
    # Font setup with scaling
    font_scale = max(scale_factor, 0.6)
    
    if FONTS:
        font_city = FontProperties(fname=FONTS['bold'], size=max(36 * font_scale, 18))
        font_country = FontProperties(fname=FONTS['light'], size=max(18 * font_scale, 12))
        font_coords = FontProperties(fname=FONTS['regular'], size=max(12 * font_scale, 10))
        font_verse = FontProperties(fname=FONTS['regular'], size=max(20 * font_scale, 14))
        font_title = FontProperties(fname=FONTS['bold'], size=max(16 * font_scale, 12))
        font_tagline = FontProperties(fname=FONTS['light'], size=max(10 * font_scale, 8))
    else:
        font_city = FontProperties(family='sans-serif', weight='bold', size=max(36 * font_scale, 18))
        font_country = FontProperties(family='sans-serif', weight='light', size=max(18 * font_scale, 12))
        font_coords = FontProperties(family='sans-serif', size=max(12 * font_scale, 10))
        font_verse = FontProperties(family='sans-serif', size=max(20 * font_scale, 14))
        font_title = FontProperties(family='sans-serif', weight='bold', size=max(16 * font_scale, 12))
        font_tagline = FontProperties(family='sans-serif', weight='light', size=max(10 * font_scale, 8))
    
    text_color = theme['text']
    
    # Calculate text layout for tightening
    chars_per_line = int(40 * (W_px / 1080))
    wrapped_verse = textwrap.fill(verse_text, width=chars_per_line)
    n_lines = len(wrapped_verse.split('\n')) if verse_text else 0
    
    verse_line_height_pixels = max(20 * font_scale, 14) * 1.4
    verse_line_height_axes = verse_line_height_pixels / H_px
    verse_total_height_axes = n_lines * verse_line_height_axes
    
    # USER: "distance = one space height equal to a single line sentence"
    title_gap_axes = verse_line_height_axes
    
    if verse_title and n_lines > 0:
        # Verse text is centered at y_center
        # Title y = top of verse block + gap
        title_y = verse_position['y_center'] + (verse_total_height_axes / 2) + title_gap_axes
    elif verse_title:
        title_y = verse_position['y_center']
    else:
        title_y = verse_position['y_center']

    # Update clearing mask with exact layout
    if clear_config['enabled']:
        print("Creating verse clearing...")
        # Deep modify clear_config to reflect refined layout for mask
        dynamic_clear_config = clear_config.copy()
        
        # Estimate horizontal coverage
        lines = wrapped_verse.split('\n')
        if lines:
            max_line_len = max(len(l) for l in lines)
            # Chars_per_line spans ~80% of width. 
            # We add a bit extra for the font character variations.
            verse_width_frac = (max_line_len / chars_per_line) * 0.85
        else:
            verse_width_frac = 0.5 # Default fallback
            
        dynamic_clear_config['verse_width_fraction'] = verse_width_frac
        
        if n_lines > 0:
            # Main clearing height is the verse block height + buffer for feathering
            # Increased buffer to 0.12 total (+0.06 each side) to prevent "squeezed" look
            dynamic_clear_config['verse_height_fraction'] = verse_total_height_axes + 0.12
            # Title clearing is much closer
            dynamic_clear_config['title_y_offset'] = (verse_total_height_axes / 2) + title_gap_axes
        
        # Update verse_position x_center for the mask if desktop aligned
        mask_verse_pos = verse_position.copy()
        if is_landscape:
            if verse_position_name == 'right':
                mask_verse_pos['x_center'] = 1.0 # Anchor to right edge
            elif verse_position_name == 'left':
                mask_verse_pos['x_center'] = 0.0 # Anchor to left edge
        
        mask_rgba = create_verse_clearing_mask(W_px, H_px, dynamic_clear_config, mask_verse_pos, theme)
        if mask_rgba is not None:
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            ax.imshow(mask_rgba, extent=[xlim[0], xlim[1], ylim[0], ylim[1]],
                      aspect='auto', zorder=8, origin='lower')
    
    # Top and bottom gradients
    create_gradient_fade(ax, theme['gradient_color'], location='bottom', zorder=9, height_fraction=0.15)
    create_gradient_fade(ax, theme['gradient_color'], location='top', zorder=9, height_fraction=0.15)
    
    # Determine alignment for desktop
    ha = 'center'
    text_x = verse_position['x_center']
    if is_landscape:
        if verse_position_name == 'right':
            ha = 'right'
            text_x = 0.96 # Align with branding edge
        elif verse_position_name == 'left':
            ha = 'left'
            text_x = 0.04
    
    # --- VERSE TITLE (reference) ---
    if verse_title and clear_config['enabled']:
        ax.text(
            text_x, title_y,
            verse_title.upper(),
            transform=ax.transAxes,
            color=text_color, ha=ha, va='center',
            fontproperties=font_title, zorder=12
        )
    
    # --- VERSE TEXT ---
    if verse_text and clear_config['enabled']:
        ax.text(
            text_x, verse_position['y_center'],
            wrapped_verse,
            transform=ax.transAxes,
            color=text_color, ha=ha, va='center',
            fontproperties=font_verse, zorder=12,
            linespacing=1.4
        )
    
    # --- BOTTOM LEFT: City info ---
    bottom_y_start = 0.05  # Further down as requested
    line_spacing = 0.025
    
    # City name (spaced letters)
    spaced_city = "  ".join(list(city.upper()))
    
    # Adjust font size for long city names
    city_font_size = max(36 * font_scale, 18)
    if len(city) > 10:
        city_font_size = max(city_font_size * (10 / len(city)), 14)
    if FONTS:
        font_city_adjusted = FontProperties(fname=FONTS['bold'], size=city_font_size)
    else:
        font_city_adjusted = FontProperties(family='sans-serif', weight='bold', size=city_font_size)
    
    ax.text(0.04, bottom_y_start + line_spacing * 2, spaced_city,
            transform=ax.transAxes, color=text_color, ha='left',
            fontproperties=font_city_adjusted, zorder=12)
    
    ax.text(0.04, bottom_y_start + line_spacing, country.upper(),
            transform=ax.transAxes, color=text_color, ha='left',
            fontproperties=font_country, zorder=12)
    
    # Coordinates
    lat, lon = point
    lat_dir = 'N' if lat >= 0 else 'S'
    lon_dir = 'E' if lon >= 0 else 'W'
    coords_str = f"{abs(lat):.4f}° {lat_dir} / {abs(lon):.4f}° {lon_dir}"
    
    ax.text(0.04, bottom_y_start, coords_str,
            transform=ax.transAxes, color=text_color, alpha=0.7, ha='left',
            fontproperties=font_coords, zorder=12)
    
    # --- BOTTOM RIGHT: NOD Logo and tagline ---
    # Logo height (proportional to canvas)
    logo_height_px = int(H_px * 0.045)  # Slightly larger logo
    
    logo_img = render_logo_with_color(theme, logo_height_px)
    
    if logo_img is not None:
        logo_width_px, _ = logo_img.size
        # Position logo in bottom right
        logo_x_frac = 0.96 - (logo_width_px / W_px)
        logo_y_frac = bottom_y_start + line_spacing - 0.005 # Center horizontally with country name
        
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        x_range = xlim[1] - xlim[0]
        y_range = ylim[1] - ylim[0]
        
        logo_extent = [
            xlim[0] + x_range * logo_x_frac,
            xlim[0] + x_range * logo_x_frac + x_range * (logo_width_px / W_px),
            ylim[0] + y_range * logo_y_frac,
            ylim[0] + y_range * logo_y_frac + y_range * (logo_height_px / H_px)
        ]
        
        ax.imshow(logo_img, extent=logo_extent, aspect='auto', zorder=12)
    
    # Tagline below logo, aligned with coordinates
    tagline_y = bottom_y_start
    ax.text(0.96, tagline_y, "Number Our Days",
            transform=ax.transAxes, color=text_color, alpha=0.8, ha='right',
            fontproperties=font_tagline, zorder=12, style='italic')
    
    # --- ATTRIBUTION (hidden - same color as background) ---
    if FONTS:
        font_attr = FontProperties(fname=FONTS['light'], size=6)
    else:
        font_attr = FontProperties(family='sans-serif', size=6)
    
    ax.text(0.98, 0.01, "© OpenStreetMap",
            transform=ax.transAxes, color=theme['bg'], alpha=0.3, ha='right', va='bottom',
            fontproperties=font_attr, zorder=12)
    
    # Remove axes
    ax.set_axis_off()
    
    # Generate output filename
    output_file = generate_output_filename(city, theme_name, preset, output_format)
    
    print(f"Saving to {output_file}...")
    
    # Save with high quality
    save_kwargs = {
        'facecolor': theme['bg'],
        'bbox_inches': 'tight',
        'pad_inches': 0,
        'dpi': max(W_px, H_px) / max(fig_width, fig_height),
    }
    
    # Save to buffer first for post-processing
    buf = io.BytesIO()
    plt.savefig(buf, format='png', **save_kwargs)
    buf.seek(0)
    plt.close()
    
    # Post-process with PIL
    img = Image.open(buf).convert('RGB')
    
    # Resize to exact dimensions
    if img.size != (W_px, H_px):
        img = img.resize((W_px, H_px), Image.LANCZOS)
    
    # Save in requested format
    fmt = output_format.lower()
    if fmt == 'png':
        img.save(output_file, 'PNG', optimize=True)
    elif fmt == 'webp':
        img.save(output_file, 'WEBP', quality=90, method=6)
    elif fmt == 'avif':
        try:
            img.save(output_file, 'AVIF', quality=80)
        except Exception as e:
            print(f"⚠ AVIF not supported: {e}. Saving as PNG.")
            output_file = output_file.replace('.avif', '.png')
            img.save(output_file, 'PNG', optimize=True)
    else:
        img.save(output_file, 'PNG', optimize=True)
    
    print(f"✓ Done! Wallpaper saved as {output_file}")
    return output_file


# =============================================================================
# CLI INTERFACE
# =============================================================================

def print_examples():
    """Print usage examples."""
    print("""
Verse Wallpaper Generator for NOD App
=====================================

Usage:
  python create_verse_wallpaper.py --city <city> --country <country> [options]

Examples:
  # Simple mobile wallpaper with verse
  python create_verse_wallpaper.py -c "Nairobi" -C "Kenya" -t noir --preset mobile `
      --verse "Teach us to number our days." --title "Psalm 90:12"
  
  # Desktop wallpaper with verse on right side
  python create_verse_wallpaper.py -c "Paris" -C "France" -t midnight_blue --preset desktop `
      --verse "Be still and know that I am God." --title "Psalm 46:10" `
      --verse-position right
  
  # Plain map without clearing
  python create_verse_wallpaper.py -c "Tokyo" -C "Japan" -t japanese_ink --preset mobile_hd `
      --clear-size none
  
  # Long verse with large clearing
  python create_verse_wallpaper.py -c "London" -C "UK" -t ocean --preset mobile `
      --verse "Trust in the LORD with all your heart..." --title "Proverbs 3:5-6"

Options:
  --city, -c          City name (required)
  --country, -C       Country name (required)
  --theme, -t         Theme name (default: noir)
  --preset, -p        Resolution: mobile, mobile_hd, desktop, desktop_hd, stories,
                      mobile_max, desktop_max, ultra_hd
  --distance, -d      Map radius in meters (default: 15000)
  --verse             Verse text to display
  --title             Verse reference/title
  --verse-position    For desktop: center, left, right, above, below
  --clear-size        Clearing size: none, thin, mid, large (auto if not set)
  --format, -f        Output format: png, webp, avif
  --list-themes       List all available themes

Presets:
  mobile      1080x1920 (standard mobile)
  mobile_hd   1440x2560 (high-DPI mobile)
  desktop     1920x1080 (standard desktop)
  desktop_hd  2560x1440 (high-DPI desktop)
  stories     1080x1920 (Instagram stories)
  mobile_max  1800x2400 (Max mobile quality)
  desktop_max 2400x3200 (Max desktop quality)
  ultra_hd    3600x4800 (Absolute maximum quality)
""")


def list_themes():
    """List all available themes."""
    available_themes = get_available_themes()
    if not available_themes:
        print("No themes found in 'themes/' directory.")
        return
    
    print("\nAvailable Themes:")
    print("-" * 60)
    for theme_name in available_themes:
        theme_path = os.path.join(THEMES_DIR, f"{theme_name}.json")
        try:
            with open(theme_path, 'r') as f:
                theme_data = json.load(f)
                display_name = theme_data.get('name', theme_name)
                description = theme_data.get('description', '')
                bg = theme_data.get('bg', '#000000')
                text = theme_data.get('text', '#FFFFFF')
        except:
            display_name = theme_name
            description = ''
            bg = '?'
            text = '?'
        
        print(f"  {theme_name}")
        print(f"    {display_name} (bg: {bg}, text: {text})")
        if description:
            print(f"    {description}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate verse wallpapers for the NOD App",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_verse_wallpaper.py -c "Nairobi" -C "Kenya" -t noir --verse "Teach us to number our days."
  python create_verse_wallpaper.py -c "Paris" -C "France" -t midnight_blue --preset desktop --verse-position right
        """
    )
    
    parser.add_argument('--city', '-c', type=str, help='City name')
    parser.add_argument('--country', '-C', type=str, help='Country name')
    parser.add_argument('--theme', '-t', type=str, default='noir', help='Theme name')
    parser.add_argument('--preset', '-p', type=str, default='mobile',
                        choices=list(PRESETS.keys()), help='Resolution preset')
    parser.add_argument('--distance', '-d', type=int, default=15000, help='Map radius in meters')
    parser.add_argument('--verse', type=str, default='', help='Verse text')
    parser.add_argument('--title', type=str, default='', help='Verse reference/title')
    parser.add_argument('--verse-position', type=str, default='center',
                        choices=list(VERSE_POSITIONS.keys()), help='Verse position for desktop')
    parser.add_argument('--clear-size', type=str, default=None,
                        choices=list(CLEARING_CONFIG.keys()), help='Clearing size override')
    parser.add_argument('--format', '-f', type=str, default='png',
                        choices=['png', 'webp', 'avif'], help='Output format')
    parser.add_argument('--list-themes', action='store_true', help='List available themes')
    
    args = parser.parse_args()
    
    if len(os.sys.argv) == 1:
        print_examples()
        os.sys.exit(0)
    
    if args.list_themes:
        list_themes()
        os.sys.exit(0)
    
    if not args.city or not args.country:
        print("Error: --city and --country are required.\n")
        print_examples()
        os.sys.exit(1)
    
    available_themes = get_available_themes()
    if args.theme not in available_themes:
        print(f"Error: Theme '{args.theme}' not found.")
        print(f"Available themes: {', '.join(available_themes)}")
        os.sys.exit(1)
    
    print("=" * 60)
    print("Verse Wallpaper Generator for NOD App")
    print("=" * 60)
    
    try:
        coords = get_coordinates(args.city, args.country)
        output_file = create_verse_wallpaper(
            city=args.city,
            country=args.country,
            point=coords,
            dist=args.distance,
            verse_text=args.verse,
            verse_title=args.title,
            theme_name=args.theme,
            preset=args.preset,
            output_format=args.format,
            verse_position_name=args.verse_position,
            clear_size=args.clear_size
        )
        
        print("\n" + "=" * 60)
        print("✓ Wallpaper generation complete!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        os.sys.exit(1)
