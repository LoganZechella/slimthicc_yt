#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting build process for Slim Thicc Command Center..."

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist
rm -rf venv_x86_64 venv_arm64

# Create virtual environments for both architectures
echo "🏗️  Creating virtual environments..."
python3 -m venv venv_x86_64
python3 -m venv venv_arm64

# Install dependencies for x86_64
echo "📦 Installing dependencies for Intel (x86_64)..."
arch -x86_64 ./venv_x86_64/bin/pip install -r requirements.txt

# Install dependencies for arm64
echo "📦 Installing dependencies for Apple Silicon (arm64)..."
arch -arm64 ./venv_arm64/bin/pip install -r requirements.txt

# Build for x86_64
echo "🔨 Building Intel (x86_64) version..."
arch -x86_64 ./venv_x86_64/bin/pyinstaller playlist_run_qt.spec --distpath dist/x86_64

# Build for arm64
echo "🔨 Building Apple Silicon (arm64) version..."
arch -arm64 ./venv_arm64/bin/pyinstaller playlist_run_qt.spec --distpath dist/arm64

# Create universal binary
echo "🔄 Creating universal binary..."
mkdir -p dist/universal
cp -R dist/x86_64/"Slim Thicc Command Center.app" dist/universal/
rm -rf dist/universal/"Slim Thicc Command Center.app"/Contents/MacOS/"Slim Thicc Command Center"
lipo "dist/x86_64/Slim Thicc Command Center.app/Contents/MacOS/Slim Thicc Command Center" "dist/arm64/Slim Thicc Command Center.app/Contents/MacOS/Slim Thicc Command Center" -create -output "dist/universal/Slim Thicc Command Center.app/Contents/MacOS/Slim Thicc Command Center"

# Create zip archive
echo "📦 Creating zip archive..."
cd dist/universal
zip -r "../Slim Thicc Command Center.app.zip" "Slim Thicc Command Center.app"
cd ../..

echo "✨ Build complete! Universal app bundle created at dist/universal/Slim Thicc Command Center.app"
echo "📦 Zip archive created at dist/Slim Thicc Command Center.app.zip"
