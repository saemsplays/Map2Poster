# CybUrban Complete Sync Script
# Full directory sync from PROJKT to D:/NOD/nod v004
# Preserves .git, node_modules and other sensitive directories

$SourceDir = "d:\PROJKT\maptoposter\nod v004"
$DestDir = "D:\NOD\nod v004"

Write-Host "Starting Complete CybUrban Sync..."
Write-Host "Source: $SourceDir"
Write-Host "Target: $DestDir"
Write-Host ""

# Use robocopy for efficient incremental sync
# /E = copy subdirectories including empty ones
# /XD = exclude directories
# /R:0 = no retries on failed copies
# /W:0 = no wait between retries

Write-Host "Syncing src directory..."
robocopy "$SourceDir\src" "$DestDir\src" /E /XD node_modules .git /R:0 /W:0 /NFL /NDL /NJH /NJS

Write-Host "Syncing public directory..."
robocopy "$SourceDir\public" "$DestDir\public" /E /XD node_modules .git /R:0 /W:0 /NFL /NDL /NJH /NJS

# Sync root-level config files
$RootFiles = @(
    "package.json",
    "tsconfig.json",
    "vite.config.ts",
    "tailwind.config.ts",
    "postcss.config.js",
    "index.html",
    "components.json"
)

Write-Host "Syncing root config files..."
foreach ($file in $RootFiles) {
    $srcPath = Join-Path $SourceDir $file
    if (Test-Path $srcPath) {
        Copy-Item -Path $srcPath -Destination (Join-Path $DestDir $file) -Force
        Write-Host "  - $file"
    }
}

# Sync supabase directory if exists
$supabaseSrc = Join-Path $SourceDir "supabase"
if (Test-Path $supabaseSrc) {
    Write-Host "Syncing Supabase directory..."
    robocopy $supabaseSrc (Join-Path $DestDir "supabase") /E /R:0 /W:0 /NFL /NDL /NJH /NJS
}

Write-Host ""
Write-Host "Complete Sync Finished!"
Write-Host "All changes ported to $DestDir"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. cd D:\NOD\nod v004"
Write-Host "  2. git add -A"
Write-Host "  3. git commit -m 'Phase 3: Scripture Engine, Fuzzy Search, M-Pesa 2026'"
Write-Host "  4. git push"
