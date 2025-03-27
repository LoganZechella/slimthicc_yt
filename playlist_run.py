import os
import sys
import time
import threading
import yt_dlp
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import platform
import spotify_handler  # Import our Spotify handler
import platform_utils  # Import our platform utilities

def get_base_path():
    return platform_utils.get_base_path()

# Specify the path to the local ffmpeg binary
def get_ffmpeg_path():
    return platform_utils.get_ffmpeg_path()

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

# Helper functions to update the GUI safely from the download thread
def update_status(msg):
    root.after(0, lambda: (log_text.insert(tk.END, msg + "\n"), log_text.see(tk.END)))

def update_progress_label(text):
    root.after(0, lambda: progress_label.config(text=text))

def enable_start_button():
    root.after(0, lambda: start_button.config(state=tk.NORMAL))

def disable_start_button():
    root.after(0, lambda: start_button.config(state=tk.DISABLED))

def get_youtube_tasks(playlist_url):
    tasks = []
    with yt_dlp.YoutubeDL({'extract_flat': True}) as ydl:
        result = ydl.extract_info(playlist_url, download=False)
        if 'entries' in result:
            for entry in result['entries']:
                video_url = entry.get('url')
                title = entry.get('title', 'Untitled Video')
                tasks.append({'query': video_url, 'title': title})
    return tasks

def process_download(youtube_url, spotify_url, download_dir):
    tasks = []
    
    # Process YouTube playlist if provided
    if youtube_url:
        try:
            yt_tasks = get_youtube_tasks(youtube_url)
            tasks.extend(yt_tasks)
            update_status(f"Found {len(yt_tasks)} tracks in the YouTube playlist.")
        except Exception as e:
            update_status(f"Error processing YouTube playlist: {str(e)}")
    
    # Process Spotify playlist if provided
    if spotify_url:
        try:
            spotify_tasks = spotify_handler.get_spotify_playlist_tracks(spotify_url)
            # Prepend "ytsearch1:" to force a YouTube search if not already a URL
            for task in spotify_tasks:
                if "://" not in task['query']:
                    task['query'] = "ytsearch1:" + task['query']
            tasks.extend(spotify_tasks)
            update_status(f"Found {len(spotify_tasks)} tracks in the Spotify playlist.")
        except Exception as e:
            update_status(f"Error processing Spotify playlist: {str(e)}")
    
    total_tasks = len(tasks)
    if total_tasks == 0:
        update_status("No tracks found to download.")
        enable_start_button()
        return

    # Set the progress bar maximum value
    root.after(0, lambda: progress_bar.config(maximum=total_tasks, value=0))
    
    failed_tasks = []
    cumulative_time = 0.0
    completed_tasks = 0
    start_overall = time.time()

    for i, task in enumerate(tasks):
        task_title = task.get('title', f"Track {i+1}")
        update_progress_label(f"Processing ({i+1}/{total_tasks}): {task_title}")
        update_status(f"Starting download for: {task_title}")
        
        start_time = time.time()
        try:
            download_video(task['query'], download_dir)
            completed_tasks += 1
        except Exception as e:
            failed_tasks.append(task_title)
            update_status(f"Failed: {task_title} with error: {str(e)}")
        
        end_time = time.time()
        elapsed = end_time - start_time
        cumulative_time += elapsed
        
        # Update progress information
        average_time = cumulative_time / (i + 1)
        remaining_tasks = total_tasks - (i + 1)
        estimated_remaining = average_time * remaining_tasks
        
        update_progress_label(
            f"Downloaded {completed_tasks}/{total_tasks}. Current: {task_title}. "
            f"Avg: {average_time:.2f}s, Estimated remaining: {estimated_remaining:.2f}s"
        )
        root.after(0, lambda i=i: progress_bar.config(value=i+1))

    total_elapsed = time.time() - start_overall
    final_message = f"Download completed. {completed_tasks} tracks processed in {total_elapsed:.2f}s."
    if failed_tasks:
        final_message += f"\nFailed tracks ({len(failed_tasks)}): " + ", ".join(failed_tasks)
    
    update_status(final_message)
    root.after(0, lambda: messagebox.showinfo("Download Completed", final_message))
    enable_start_button()

def start_download():
    youtube_url = youtube_entry.get().strip()
    spotify_url = spotify_entry.get().strip()
    download_dir = dir_entry.get().strip()

    if not (youtube_url or spotify_url):
        messagebox.showerror("Error", "Please enter at least one playlist URL (YouTube or Spotify).")
        return
        
    if not download_dir:
        messagebox.showerror("Error", "Please select a download directory.")
        return

    # Create download directory if it doesn't exist
    os.makedirs(download_dir, exist_ok=True)
    
    disable_start_button()
    # Start download in a separate thread to keep the GUI responsive
    threading.Thread(target=process_download, args=(youtube_url, spotify_url, download_dir), daemon=True).start()

def browse_directory():
    # Use platform-specific default directory
    default_dir = platform_utils.get_app_data_dir()
    folder_selected = filedialog.askdirectory(initialdir=default_dir)
    if folder_selected:  # Only update if a folder was selected
        dir_entry.delete(0, tk.END)
        dir_entry.insert(0, folder_selected)

# Create the main window
root = tk.Tk()
root.title("Playlist Downloader")
root.geometry("900x700")  # Larger initial size
root.configure(background="#121212")
# Set initial transparency to 0 (for fade in)
root.attributes("-alpha", 0.0)

# Set up the style for a dark look with green accents.
style = ttk.Style()
style.theme_use("clam")

# Configure primary colors - adjust colors for better visibility on Raspberry Pi if needed
bg_color = "#121212"            # dark background
fg_color = "#FFFFFF"            # white text
entry_bg = "#2c2c2c"            # dark entry background

# Check if running on Raspberry Pi and adjust accordingly
if platform_utils.is_raspberry_pi():
    # Adjust font sizes and button sizes for Raspberry Pi touchscreens
    default_font = ("Helvetica", 14)  # Slightly smaller for Pi screens
    large_font = ("Helvetica", 16, "bold")  
    button_font = ("Helvetica", 14, "bold")
    # Adjust accent color for better contrast on Pi displays
    accent_color = "#22CC66"    # brighter green for better visibility
    accent_hover = "#25DD70"    # brighter hover for Pi screens
else:
    # Regular settings for other platforms
    default_font = ("Helvetica", 16)  # Increased font size
    large_font = ("Helvetica", 18, "bold")  # For headers
    button_font = ("Helvetica", 16, "bold")  # For buttons
    accent_color = "#1DB954"    # spotify-inspired green
    accent_hover = "#1ED760"    # lighter green on hover

# Configure ttk widget styles
style.configure("Title.TLabel", 
                background=bg_color, 
                foreground=fg_color, 
                font=large_font, 
                padding=15)

style.configure("TLabel", 
                background=bg_color, 
                foreground=fg_color, 
                font=default_font, 
                padding=10)

style.configure("TEntry", 
                foreground=fg_color, 
                fieldbackground=entry_bg, 
                background=entry_bg, 
                font=default_font, 
                padding=10)

style.configure("TButton", 
                background=accent_color, 
                foreground=fg_color, 
                font=button_font, 
                padding=15)

style.map("TButton", 
          background=[("active", accent_hover)],
          relief=[("pressed", "groove"), ("!pressed", "ridge")])

style.configure("TProgressbar", 
                troughcolor="#1f1f1f", 
                background=accent_color,
                thickness=25)  # Thicker progress bar

# Create a master frame with padding
main_frame = ttk.Frame(root, padding="30 30 30 30", style="TFrame")
main_frame.pack(fill=tk.BOTH, expand=True)

# Configure grid columns and rows to be responsive
main_frame.columnconfigure(1, weight=3)  # Make the middle column (with entries) expand more
main_frame.columnconfigure(0, weight=1)  # Label column
main_frame.columnconfigure(2, weight=1)  # Button column

for i in range(7):  # Configure all rows to be expandable
    main_frame.rowconfigure(i, weight=1)

# Title label
title_label = ttk.Label(main_frame, text="Playlist Downloader", style="Title.TLabel")
title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

# Create and place input fields and labels
ttk.Label(main_frame, text="YouTube Playlist URL:").grid(row=1, column=0, sticky="e", padx=10)
youtube_entry = ttk.Entry(main_frame)
youtube_entry.grid(row=1, column=1, sticky="ew", padx=10)

ttk.Label(main_frame, text="Spotify Playlist URL:").grid(row=2, column=0, sticky="e", padx=10)
spotify_entry = ttk.Entry(main_frame)
spotify_entry.grid(row=2, column=1, sticky="ew", padx=10)

ttk.Label(main_frame, text="Download Directory:").grid(row=3, column=0, sticky="e", padx=10)
dir_entry = ttk.Entry(main_frame)
dir_entry.grid(row=3, column=1, sticky="ew", padx=10)
browse_btn = ttk.Button(main_frame, text="Browse", command=browse_directory)
browse_btn.grid(row=3, column=2, padx=10, sticky="w")

# Progress section frame
progress_frame = ttk.Frame(main_frame)
progress_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=20)
progress_frame.columnconfigure(0, weight=1)

# Create Progress Bar and progress label
progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate")
progress_bar.grid(row=0, column=0, sticky="ew", padx=20, pady=10)

progress_label = ttk.Label(progress_frame, text="Ready to start download...", 
                          wraplength=800, justify="center")
progress_label.grid(row=1, column=0, sticky="ew", pady=10)

# Create log text widget with custom styling
log_frame = ttk.Frame(main_frame)
log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=10)
log_frame.columnconfigure(0, weight=1)
log_frame.rowconfigure(0, weight=1)

log_text = tk.Text(log_frame, 
                  font=("Helvetica", 14),
                  background="#1e1e1e", 
                  foreground=fg_color, 
                  relief=tk.FLAT, 
                  bd=0, 
                  highlightthickness=1,
                  highlightbackground=accent_color,
                  highlightcolor=accent_color,
                  padx=10,
                  pady=10)
log_text.grid(row=0, column=0, sticky="nsew")
log_text.insert(tk.END, "Log:\n")

# Add scrollbar to log text
scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
scrollbar.grid(row=0, column=1, sticky="ns")
log_text.configure(yscrollcommand=scrollbar.set)

# Button frame for centered button
button_frame = ttk.Frame(main_frame)
button_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=20)
button_frame.columnconfigure(0, weight=1)

# Start Download button
start_button = ttk.Button(button_frame, text="Start Download", command=start_download)
start_button.grid(row=0, column=0)

# ------------------- OPENING FADE-IN ANIMATION -------------------
def fade_in(window, current=0.0, step=0.05):
    current += step
    if current > 1.0:
        window.attributes("-alpha", 1.0)
    else:
        window.attributes("-alpha", current)
        window.after(50, fade_in, window, current, step)

# Center the window on the screen
root.update_idletasks()
width = root.winfo_width()
height = root.winfo_height()
x = (root.winfo_screenwidth() // 2) - (width // 2)
y = (root.winfo_screenheight() // 2) - (height // 2)
root.geometry(f"+{x}+{y}")

# Begin fade-in animation
fade_in(root)

# Start the GUI event loop
root.mainloop()
