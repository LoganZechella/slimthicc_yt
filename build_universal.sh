#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting build process for Slim Thicc Command Center..."

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist

# Build Intel (x86_64) version
echo "Building Intel (x86_64) version..."
source venv_x86_64/bin/activate
arch -x86_64 python3 -m PyInstaller "Slim Thicc Command Center.spec" --distpath dist/x86_64
deactivate

# Build ARM64 version
echo "Building Apple Silicon (arm64) version..."
source venv/bin/activate
python3 -m PyInstaller "Slim Thicc Command Center.spec" --distpath dist/arm64
deactivate

# Create universal binary
echo "🔄 Creating universal binary..."
mkdir -p dist/universal
cp -R dist/arm64/"Slim Thicc Command Center.app" dist/universal/

# Replace the binary with a universal binary
rm -f dist/universal/"Slim Thicc Command Center.app/Contents/MacOS/Slim Thicc Command Center"
lipo "dist/x86_64/Slim Thicc Command Center.app/Contents/MacOS/Slim Thicc Command Center" \
     "dist/arm64/Slim Thicc Command Center.app/Contents/MacOS/Slim Thicc Command Center" \
     -create -output "dist/universal/Slim Thicc Command Center.app/Contents/MacOS/Slim Thicc Command Center"

# Create zip archive
echo "📦 Creating zip archive..."
cd dist/universal
zip -r "../Slim Thicc Command Center.app.zip" "Slim Thicc Command Center.app"
cd ../..

echo "✨ Build complete! Universal app bundle created at dist/universal/Slim Thicc Command Center.app"
echo "📦 Zip archive created at dist/Slim Thicc Command Center.app.zip"
