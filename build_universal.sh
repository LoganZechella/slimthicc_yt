#!/bin/bash

# Build ARM64 version
source venv_arm64/bin/activate
pip install -r requirements.txt
pyinstaller playlist_run.spec
mv dist/playlist_run.app dist/playlist_run_arm64.app
deactivate

# Build x86_64 version
source venv_x86_64/bin/activate
arch -x86_64 pip install -r requirements.txt
arch -x86_64 pyinstaller playlist_run.spec
mv dist/playlist_run.app dist/playlist_run_x86_64.app
deactivate

# Combine into universal binary
mkdir -p dist/playlist_run_universal.app/Contents/MacOS
lipo dist/playlist_run_arm64.app/Contents/MacOS/playlist_run dist/playlist_run_x86_64.app/Contents/MacOS/playlist_run -create -output dist/playlist_run_universal.app/Contents/MacOS/playlist_run

# Copy other necessary files
cp -R dist/playlist_run_arm64.app/Contents/Resources dist/playlist_run_universal.app/Contents/
cp dist/playlist_run_arm64.app/Contents/Info.plist dist/playlist_run_universal.app/Contents/

# Clean up
rm -rf dist/playlist_run_arm64.app dist/playlist_run_x86_64.app

echo "Universal app created at dist/playlist_run_universal.app"
