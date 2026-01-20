"""
Mock Render Verification for Verse Wallpaper
=============================================
Creates mock wallpaper layouts WITHOUT API calls to OpenStreetMap.
This allows rapid visual testing of layouts, clearing zones, and branding.

Usage:
    python mock_render_verification.py
    
Generates test outputs in posters/mock_tests/ directory.
"""

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import numpy as np
from scipy.ndimage import gaussian_filter
import os
from datetime import datetime
from PIL import Image
import io
import textwrap

# No external SVG libraries needed - using PNG logos with PIL color tinting

# Import shared utilities from main module
import json

# =============================================================================
# CONSTANTS (duplicated for standalone use)
# =============================================================================

THEMES_DIR = "themes"
FONTS_DIR = "fonts"
POSTERS_DIR = "posters"
MOCK_DIR = os.path.join(POSTERS_DIR, "mock_tests")
ASSETS_DIR = "."

PRESETS = {
    'mobile': (1080, 1920),
    'mobile_hd': (1440, 2560),
    'desktop': (1920, 1080),
    'desktop_hd': (2560, 1440),
    'stories': (1080, 1920),
}

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

TITLE_WIDTH_FRACTION = 0.5
TITLE_GAP_FRACTION = 0.02
VERSE_Y_CENTER = 0.58
MAX_ALPHA = 0.92
FEATHER_SIGMA_FRACTION = 0.35

VERSE_POSITIONS = {
    'center': {'x_center': 0.5, 'y_center': 0.58},
    'left': {'x_center': 0.25, 'y_center': 0.55},
    'right': {'x_center': 0.75, 'y_center': 0.55},
    'above': {'x_center': 0.5, 'y_center': 0.70},
    'below': {'x_center': 0.5, 'y_center': 0.40},
}

# Sample verses for testing
SAMPLE_VERSES = {
    'thin': {
        'text': "Teach us to number our days.",
        'title': "Psalm 90:12"
    },
    'mid': {
        'text': "For I know the plans I have for you, declares the LORD, plans for welfare and not for evil, to give you a future and a hope.",
        'title': "Jeremiah 29:11"
    },
    'large': {
        'text': "Trust in the LORD with all your heart, and do not lean on your own understanding. In all your ways acknowledge him, and he will make straight your paths. Be not wise in your own eyes; fear the LORD, and turn away from evil. It will be healing to your flesh and refreshment to your bones.",
        'title': "Proverbs 3:5-8"
    }
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def load_fonts():
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


def load_theme(theme_name):
    theme_file = os.path.join(THEMES_DIR, f"{theme_name}.json")
    if not os.path.exists(theme_file):
        return {
            "name": "Default",
            "bg": "#1a1a1a",
            "text": "#ffffff",
            "gradient_color": "#1a1a1a",
        }
    with open(theme_file, 'r') as f:
        return json.load(f)


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def compute_relative_luminance(hex_color):
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


def get_logo_png_path(theme):
    """Determine which logo PNG to use based on theme background luminance."""
    bg_luminance = compute_relative_luminance(theme['bg'])
    if bg_luminance < 0.5:
        return os.path.join(ASSETS_DIR, 'NOD-LOGO-dark.png')
    else:
        return os.path.join(ASSETS_DIR, 'NOD-LOGO-light.png')


def render_logo_with_color(theme, size):
    """
    Render logo at specified size with theme's text color.
    Uses PNG base with PIL color tinting.
    """
    logo_path = get_logo_png_path(theme)
    target_color = hex_to_rgb(theme['text'])
    
    if not os.path.exists(logo_path):
        print(f"⚠ Logo PNG not found: {logo_path}")
        return None
    
    try:
        logo = Image.open(logo_path).convert('RGBA')
        logo = logo.resize(size, Image.LANCZOS)
        r, g, b, a = logo.split()
        color_layer = Image.new('RGBA', logo.size, target_color + (255,))
        color_layer.putalpha(a)
        return color_layer
    except Exception as e:
        print(f"⚠ Error rendering logo: {e}")
        return None


def create_verse_clearing_mask(W_px, H_px, clear_config, verse_position, theme):
    if not clear_config['enabled']:
        return None
    
    clear_color_rgb = hex_to_rgb(theme['bg'])
    y_coords = np.linspace(0, 1, H_px)
    x_coords = np.linspace(0, 1, W_px)
    
    verse_height_frac = clear_config['verse_height_fraction']
    title_height_frac = clear_config['title_height_fraction']
    
    y_center = verse_position['y_center']
    x_center = verse_position['x_center']
    
    h_main = verse_height_frac / 2
    sigma_main = FEATHER_SIGMA_FRACTION * verse_height_frac
    
    main_alpha = np.zeros((H_px, W_px), dtype=np.float32)
    
    for i, y in enumerate(y_coords):
        d = (y - y_center) / h_main if h_main > 0 else 0
        alpha_val = MAX_ALPHA * np.exp(-0.5 * (d / sigma_main) ** 2) if sigma_main > 0 else 0
        main_alpha[i, :] = np.clip(alpha_val, 0, MAX_ALPHA)
    
    title_alpha = np.zeros((H_px, W_px), dtype=np.float32)
    title_y_center = y_center + h_main + TITLE_GAP_FRACTION + title_height_frac / 2
    h_title = title_height_frac / 2
    sigma_title = FEATHER_SIGMA_FRACTION * title_height_frac
    
    title_x_left = x_center - TITLE_WIDTH_FRACTION / 2
    title_x_right = x_center + TITLE_WIDTH_FRACTION / 2
    
    for i, y in enumerate(y_coords):
        d_y = (y - title_y_center) / h_title if h_title > 0 else 0
        alpha_y = np.exp(-0.5 * (d_y / sigma_title) ** 2) if sigma_title > 0 else 0
        
        for j, x in enumerate(x_coords):
            if x < title_x_left:
                d_x = (title_x_left - x) / (sigma_title * 0.5)
                alpha_x = np.exp(-0.5 * d_x ** 2)
            elif x > title_x_right:
                d_x = (x - title_x_right) / (sigma_title * 0.5)
                alpha_x = np.exp(-0.5 * d_x ** 2)
            else:
                alpha_x = 1.0
            
            title_alpha[i, j] = MAX_ALPHA * 0.85 * alpha_y * alpha_x
    
    combined_alpha = np.maximum(main_alpha, title_alpha)
    blur_sigma = max(H_px, W_px) * 0.008
    combined_alpha = gaussian_filter(combined_alpha, sigma=blur_sigma)
    combined_alpha = np.clip(combined_alpha, 0, MAX_ALPHA)
    
    mask_rgba = np.zeros((H_px, W_px, 4), dtype=np.uint8)
    mask_rgba[:, :, 0] = clear_color_rgb[0]
    mask_rgba[:, :, 1] = clear_color_rgb[1]
    mask_rgba[:, :, 2] = clear_color_rgb[2]
    mask_rgba[:, :, 3] = (combined_alpha * 255).astype(np.uint8)
    
    return mask_rgba


def create_gradient_fade(ax, color, location='bottom', zorder=10, height_fraction=0.25):
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
# MOCK MAP GENERATOR
# =============================================================================

def create_mock_map_pattern(ax, theme, pattern_type='grid'):
    """Create a mock map pattern for visual testing."""
    xlim = (0, 1)
    ylim = (0, 1)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    
    # Background
    ax.set_facecolor(theme['bg'])
    
    # Get road colors from theme
    road_colors = [
        theme.get('road_motorway', '#888888'),
        theme.get('road_primary', '#666666'),
        theme.get('road_secondary', '#555555'),
        theme.get('road_tertiary', '#444444'),
        theme.get('road_residential', '#333333'),
    ]
    
    if pattern_type == 'grid':
        # Create a grid-like pattern
        np.random.seed(42)
        
        # Major roads (fewer, thicker)
        for i in range(5):
            x = 0.1 + i * 0.2
            ax.plot([x, x], [0, 1], color=road_colors[0], linewidth=1.5, zorder=3)
            ax.plot([0, 1], [x, x], color=road_colors[0], linewidth=1.5, zorder=3)
        
        # Secondary roads
        for i in range(10):
            x = 0.05 + i * 0.1
            if abs(x % 0.2 - 0.1) > 0.01:
                ax.plot([x, x], [0, 1], color=road_colors[2], linewidth=0.8, zorder=2)
                ax.plot([0, 1], [x, x], color=road_colors[2], linewidth=0.8, zorder=2)
        
        # Residential roads (many, thin)
        for i in range(30):
            x = i / 30
            y = (i * 7 % 30) / 30
            ax.plot([x, x + 0.05], [y, y], color=road_colors[4], linewidth=0.4, zorder=1)
            ax.plot([x, x], [y, y + 0.05], color=road_colors[4], linewidth=0.4, zorder=1)
    
    elif pattern_type == 'organic':
        # Create organic-looking paths
        np.random.seed(42)
        for i in range(20):
            x_start = np.random.random()
            y_start = np.random.random()
            angles = np.cumsum(np.random.randn(10) * 0.3)
            x_points = [x_start]
            y_points = [y_start]
            for angle in angles:
                x_points.append(x_points[-1] + 0.05 * np.cos(angle))
                y_points.append(y_points[-1] + 0.05 * np.sin(angle))
            color = road_colors[i % len(road_colors)]
            width = 1.2 - (i % 5) * 0.2
            ax.plot(x_points, y_points, color=color, linewidth=width, zorder=3-i%3)
    
    # Add some "water" features
    water_color = theme.get('water', '#1a1a1a')
    water_patches = [
        mpatches.Circle((0.85, 0.75), 0.08, facecolor=water_color, edgecolor='none'),
        mpatches.Circle((0.15, 0.25), 0.05, facecolor=water_color, edgecolor='none'),
    ]
    for patch in water_patches:
        ax.add_patch(patch)
    
    # Add some "park" features
    parks_color = theme.get('parks', '#222222')
    park_patches = [
        mpatches.Rectangle((0.6, 0.3), 0.15, 0.1, facecolor=parks_color, edgecolor='none'),
        mpatches.Rectangle((0.2, 0.7), 0.1, 0.15, facecolor=parks_color, edgecolor='none'),
    ]
    for patch in park_patches:
        ax.add_patch(patch)


# =============================================================================
# MOCK WALLPAPER GENERATOR
# =============================================================================

def create_mock_wallpaper(
    city="Nairobi",
    country="Kenya",
    theme_name="noir",
    preset="mobile",
    verse_text="",
    verse_title="",
    verse_position_name="center",
    clear_size=None,
    output_name=None
):
    """Generate a mock wallpaper for layout verification."""
    
    print(f"\n{'='*60}")
    print(f"Generating mock wallpaper: {city}, {country}")
    print(f"  Theme: {theme_name}, Preset: {preset}")
    print(f"  Clear size: {clear_size or 'auto'}")
    print(f"{'='*60}")
    
    # Setup
    theme = load_theme(theme_name)
    W_px, H_px = PRESETS.get(preset, PRESETS['mobile'])
    is_landscape = W_px > H_px
    
    # Compute scale
    scale_factor = H_px / 1920
    
    # Determine clearing
    if clear_size is None:
        verse_length = len(verse_text)
        if verse_length == 0:
            clear_size = 'none'
        elif verse_length <= 60:
            clear_size = 'thin'
        elif verse_length <= 180:
            clear_size = 'mid'
        else:
            clear_size = 'large'
    
    clear_config = CLEARING_CONFIG[clear_size]
    
    print(f"  Clearing: {clear_size} (verse len: {len(verse_text)})")
    
    # Get verse position
    if is_landscape and verse_position_name in VERSE_POSITIONS:
        verse_position = VERSE_POSITIONS[verse_position_name]
    else:
        verse_position = VERSE_POSITIONS['center']
    
    # Figure setup
    dpi = 100
    fig_width = W_px / dpi
    fig_height = H_px / dpi
    
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor=theme['bg'])
    ax.set_facecolor(theme['bg'])
    ax.set_position([0, 0, 1, 1])
    
    # Create mock map
    create_mock_map_pattern(ax, theme, 'grid')
    
    # Apply clearing
    if clear_config['enabled']:
        mask_rgba = create_verse_clearing_mask(W_px, H_px, clear_config, verse_position, theme)
        if mask_rgba is not None:
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            ax.imshow(mask_rgba, extent=[xlim[0], xlim[1], ylim[0], ylim[1]],
                      aspect='auto', zorder=8, origin='lower')
    
    # Gradients
    create_gradient_fade(ax, theme.get('gradient_color', theme['bg']), 
                        location='bottom', zorder=9, height_fraction=0.20)
    create_gradient_fade(ax, theme.get('gradient_color', theme['bg']), 
                        location='top', zorder=9, height_fraction=0.18)
    
    # Typography
    font_scale = max(scale_factor, 0.6)
    text_color = theme['text']
    
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
    
    # Verse title
    if verse_title and clear_config['enabled']:
        title_y = (verse_position['y_center'] + 
                   clear_config['verse_height_fraction'] / 2 + 
                   TITLE_GAP_FRACTION + 
                   clear_config['title_height_fraction'] / 2)
        ax.text(
            verse_position['x_center'], title_y,
            verse_title.upper(),
            transform=ax.transAxes,
            color=text_color, ha='center', va='center',
            fontproperties=font_title, zorder=12
        )
    
    # Verse text
    if verse_text and clear_config['enabled']:
        chars_per_line = int(40 * (W_px / 1080))
        wrapped_verse = textwrap.fill(verse_text, width=chars_per_line)
        ax.text(
            verse_position['x_center'], verse_position['y_center'],
            wrapped_verse,
            transform=ax.transAxes,
            color=text_color, ha='center', va='center',
            fontproperties=font_verse, zorder=12,
            linespacing=1.4
        )
    
    # Bottom left: City info
    bottom_y_start = 0.22
    line_spacing = 0.025
    
    spaced_city = "  ".join(list(city.upper()))
    city_font_size = max(36 * font_scale, 18)
    if len(city) > 10:
        city_font_size = max(city_font_size * (10 / len(city)), 14)
    if FONTS:
        font_city_adjusted = FontProperties(fname=FONTS['bold'], size=city_font_size)
    else:
        font_city_adjusted = FontProperties(family='sans-serif', weight='bold', size=city_font_size)
    
    ax.text(0.04, bottom_y_start, spaced_city,
            transform=ax.transAxes, color=text_color, ha='left',
            fontproperties=font_city_adjusted, zorder=12)
    
    ax.text(0.04, bottom_y_start - line_spacing, country.upper(),
            transform=ax.transAxes, color=text_color, ha='left',
            fontproperties=font_country, zorder=12)
    
    coords_str = f"1.2864° S / 36.8172° E"  # Mock coordinates
    ax.text(0.04, bottom_y_start - line_spacing * 2, coords_str,
            transform=ax.transAxes, color=text_color, alpha=0.7, ha='left',
            fontproperties=font_coords, zorder=12)
    
    # Bottom right: Logo and tagline
    logo_height_px = int(H_px * 0.035)
    logo_width_px = int(logo_height_px * 2.5)
    
    logo_img = render_logo_with_color(theme, (logo_width_px, logo_height_px))
    
    if logo_img is not None:
        logo_x_frac = 0.96 - (logo_width_px / W_px)
        logo_y_frac = bottom_y_start - line_spacing
        
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
        print(f"  ✓ Logo rendered with color: {theme['text']}")
    else:
        # Fallback: text placeholder for logo
        ax.text(0.96, bottom_y_start - line_spacing, "NOD",
                transform=ax.transAxes, color=text_color, ha='right',
                fontproperties=font_city, zorder=12)
        print(f"  ⚠ Logo not available, using text fallback")
    
    # Tagline
    tagline_y = bottom_y_start - line_spacing * 2 - 0.005
    ax.text(0.96, tagline_y, "Number Our Days",
            transform=ax.transAxes, color=text_color, alpha=0.8, ha='right',
            fontproperties=font_tagline, zorder=12, style='italic')
    
    # Hide attribution (same color as background)
    ax.text(0.98, 0.01, "© OpenStreetMap",
            transform=ax.transAxes, color=theme['bg'], alpha=0.3, ha='right', va='bottom',
            fontproperties=font_tagline, zorder=12)
    
    ax.set_axis_off()
    
    # Save
    if not os.path.exists(MOCK_DIR):
        os.makedirs(MOCK_DIR)
    
    if output_name is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"mock_{theme_name}_{preset}_{clear_size}_{timestamp}.png"
    
    output_path = os.path.join(MOCK_DIR, output_name)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=theme['bg'], 
                bbox_inches='tight', pad_inches=0, 
                dpi=max(W_px, H_px) / max(fig_width, fig_height))
    buf.seek(0)
    plt.close()
    
    img = Image.open(buf).convert('RGB')
    if img.size != (W_px, H_px):
        img = img.resize((W_px, H_px), Image.LANCZOS)
    
    img.save(output_path, 'PNG', optimize=True)
    print(f"  ✓ Saved: {output_path}")
    
    return output_path


# =============================================================================
# TEST SUITE
# =============================================================================

def run_all_tests():
    """Run comprehensive visual tests."""
    
    print("\n" + "=" * 70)
    print("VERSE WALLPAPER MOCK VERIFICATION SUITE")
    print("=" * 70)
    
    results = []
    
    # Test 1: All clearing sizes with noir theme
    print("\n--- TEST 1: Clearing Sizes (noir theme, mobile) ---")
    for clear_size in ['none', 'thin', 'mid', 'large']:
        verse_data = SAMPLE_VERSES.get(clear_size, SAMPLE_VERSES['mid'])
        output = create_mock_wallpaper(
            city="Nairobi",
            country="Kenya",
            theme_name="noir",
            preset="mobile",
            verse_text=verse_data['text'] if clear_size != 'none' else '',
            verse_title=verse_data['title'] if clear_size != 'none' else '',
            clear_size=clear_size,
            output_name=f"test1_noir_mobile_{clear_size}.png"
        )
        results.append(output)
    
    # Test 2: Different themes
    print("\n--- TEST 2: Theme Variations (mid clearing, mobile) ---")
    themes = ['midnight_blue', 'sunset', 'ocean', 'warm_beige']
    verse = SAMPLE_VERSES['mid']
    for theme_name in themes:
        output = create_mock_wallpaper(
            city="Paris",
            country="France",
            theme_name=theme_name,
            preset="mobile",
            verse_text=verse['text'],
            verse_title=verse['title'],
            clear_size='mid',
            output_name=f"test2_{theme_name}_mobile_mid.png"
        )
        results.append(output)
    
    # Test 3: Desktop with verse positions
    print("\n--- TEST 3: Desktop Verse Positions (noir theme) ---")
    positions = ['center', 'left', 'right']
    verse = SAMPLE_VERSES['thin']
    for position in positions:
        output = create_mock_wallpaper(
            city="London",
            country="UK",
            theme_name="noir",
            preset="desktop",
            verse_text=verse['text'],
            verse_title=verse['title'],
            verse_position_name=position,
            clear_size='thin',
            output_name=f"test3_noir_desktop_{position}.png"
        )
        results.append(output)
    
    # Test 4: All presets
    print("\n--- TEST 4: Resolution Presets (noir theme, mid clearing) ---")
    verse = SAMPLE_VERSES['mid']
    for preset in ['mobile', 'mobile_hd', 'desktop', 'desktop_hd']:
        output = create_mock_wallpaper(
            city="Tokyo",
            country="Japan",
            theme_name="noir",
            preset=preset,
            verse_text=verse['text'],
            verse_title=verse['title'],
            clear_size='mid',
            output_name=f"test4_noir_{preset}_mid.png"
        )
        results.append(output)
    
    print("\n" + "=" * 70)
    print(f"COMPLETE! Generated {len(results)} test images.")
    print(f"Output directory: {os.path.abspath(MOCK_DIR)}")
    print("=" * 70)
    
    return results


if __name__ == "__main__":
    run_all_tests()
