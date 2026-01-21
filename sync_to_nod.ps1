# CybUrban Sync Script
# Ports changes from PROJKT to D:/NOD/nod v004

$SourceDir = "d:\PROJKT\maptoposter\nod v004"
$DestDir = "D:\NOD\nod v004"

echo "🚀 Starting CybUrban HAM Sync..."

# 1. Ensure directories exist
$NewDirs = @(
    "src\pages",
    "src\components",
    "public\assets\cyburban"
)

foreach ($dir in $NewDirs) {
    if (!(Test-Path "$DestDir\$dir")) {
        New-Item -ItemType Directory -Path "$DestDir\$dir" -Force
    }
}

# 2. Sync Files
$FilesToSync = @(
    "src\App.tsx",
    "src\components\VerseOfTheDay.tsx",
    "src\pages\CyburbanStudio.tsx",
    "src\components\CyburbanConfigurator.tsx",
    "src\components\CyburbanPaymentModal.tsx"
)

foreach ($file in $FilesToSync) {
    echo "📄 Syncing $file..."
    Copy-Item -Path "$SourceDir\$file" -Destination "$DestDir\$file" -Force
}

# 3. Sync Assets
echo "🖼️ Syncing Assets..."
Copy-Item -Path "$SourceDir\public\assets\cyburban\*" -Destination "$DestDir\public\assets\cyburban" -Force

echo "✅ Sync Complete! Ported to $DestDir"
