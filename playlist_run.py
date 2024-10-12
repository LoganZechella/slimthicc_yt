import os
import sys
import yt_dlp
import tkinter as tk
from tkinter import filedialog, messagebox
import platform

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

# Specify the path to the local ffmpeg binary
def get_ffmpeg_path():
    base_path = get_base_path()
    if platform.machine() == 'arm64':
        return os.path.join(base_path, 'ffmpeg_bin', 'arm64', 'ffmpeg')
    else:
        return os.path.join(base_path, 'ffmpeg_bin', 'x86_64', 'ffmpeg')

ffmpeg_path = get_ffmpeg_path()

def download_video(url, download_dir):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'ffmpeg_location': ffmpeg_path,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def start_download():
    playlist_url = url_entry.get()
    download_dir = dir_entry.get()

    if not playlist_url or not download_dir:
        messagebox.showerror("Error", "Please enter both URL and download directory.")
        return

    # Make sure the download directory exists
    os.makedirs(download_dir, exist_ok=True)

    # Download all videos in the playlist
    try:
        with yt_dlp.YoutubeDL({'extract_flat': 'in_playlist'}) as ydl:
            result = ydl.extract_info(playlist_url, download=False)
            if 'entries' in result:
                for entry in result['entries']:
                    video_url = entry['url']
                    download_video(video_url, download_dir)
        messagebox.showinfo("Success", "Download completed successfully!")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

def browse_directory():
    folder_selected = filedialog.askdirectory()
    dir_entry.delete(0, tk.END)
    dir_entry.insert(0, folder_selected)

# Create the main window
root = tk.Tk()
root.title("YouTube Playlist Downloader")

# Create and place widgets
tk.Label(root, text="Playlist URL:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
url_entry = tk.Entry(root, width=50)
url_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=5)

tk.Label(root, text="Download Directory:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
dir_entry = tk.Entry(root, width=50)
dir_entry.grid(row=1, column=1, padx=5, pady=5)
tk.Button(root, text="Browse", command=browse_directory).grid(row=1, column=2, padx=5, pady=5)

tk.Button(root, text="Start Download", command=start_download).grid(row=2, column=1, pady=10)

# Start the GUI event loop
root.mainloop()
