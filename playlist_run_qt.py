import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QGridLayout, QLabel, QLineEdit, 
                            QPushButton, QProgressBar, QTextEdit, QFileDialog,
                            QFrame, QMessageBox, QDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon
import yt_dlp
import platform
import spotify_handler
import json
import platform_utils  # Import our platform utilities

class SpotifyCredentialsDialog(QDialog):
    def __init__(self, parent=None, saved_credentials=None):
        super().__init__(parent)
        self.setWindowTitle("Spotify Credentials")
        self.setModal(True)
        self.setup_ui(saved_credentials)
        
    def setup_ui(self, saved_credentials):
        layout = QVBoxLayout(self)
        
        # Info label with more detailed instructions
        info_label = QLabel(
            "Please enter your Spotify API credentials.\n\n"
            "1. Go to https://developer.spotify.com/dashboard\n"
            "2. Log in with your Spotify account\n"
            "3. Create a new app\n"
            "4. Copy the Client ID and Client Secret\n\n"
            "Note: These credentials will be securely stored on your computer."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Client ID
        client_id_label = QLabel("Client ID:")
        self.client_id_input = QLineEdit()
        if saved_credentials and 'client_id' in saved_credentials:
            self.client_id_input.setText(saved_credentials['client_id'])
        self.client_id_input.textChanged.connect(self.validate_inputs)
        layout.addWidget(client_id_label)
        layout.addWidget(self.client_id_input)
        
        # Client Secret
        client_secret_label = QLabel("Client Secret:")
        self.client_secret_input = QLineEdit()
        if saved_credentials and 'client_secret' in saved_credentials:
            self.client_secret_input.setText(saved_credentials['client_secret'])
        self.client_secret_input.textChanged.connect(self.validate_inputs)
        layout.addWidget(client_secret_label)
        layout.addWidget(self.client_secret_input)
        
        # Error label (hidden by default)
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #ff4444;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.validate_and_accept)
        self.save_button.setEnabled(False)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                color: #ffffff;
                padding: 8px;
                font-size: 14px;
            }
            QPushButton {
                background-color: #1DB954;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1ED760;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
            }
        """)
        
        # Initial validation
        self.validate_inputs()
        
    def validate_inputs(self):
        client_id = self.client_id_input.text().strip()
        client_secret = self.client_secret_input.text().strip()
        
        if not client_id and not client_secret:
            self.error_label.hide()
            self.save_button.setEnabled(False)
            return
            
        if not client_id:
            self.error_label.setText("Client ID is required")
            self.error_label.show()
            self.save_button.setEnabled(False)
            return
            
        if not client_secret:
            self.error_label.setText("Client Secret is required")
            self.error_label.show()
            self.save_button.setEnabled(False)
            return
            
        if len(client_id) < 32:
            self.error_label.setText("Client ID appears to be invalid (should be 32 characters)")
            self.error_label.show()
            self.save_button.setEnabled(False)
            return
            
        if len(client_secret) < 32:
            self.error_label.setText("Client Secret appears to be invalid (should be 32 characters)")
            self.error_label.show()
            self.save_button.setEnabled(False)
            return
            
        self.error_label.hide()
        self.save_button.setEnabled(True)
        
    def validate_and_accept(self):
        credentials = self.get_credentials()
        try:
            # Test the credentials
            os.environ['SPOTIPY_CLIENT_ID'] = credentials['client_id']
            os.environ['SPOTIPY_CLIENT_SECRET'] = credentials['client_secret']
            spotify_handler.get_spotify_client()
            self.accept()
        except Exception as e:
            self.error_label.setText(f"Invalid credentials: {str(e)}")
            self.error_label.show()
            self.save_button.setEnabled(False)
        
    def get_credentials(self):
        return {
            'client_id': self.client_id_input.text().strip(),
            'client_secret': self.client_secret_input.text().strip()
        }

class DownloadWorker(QThread):
    """Worker thread for handling downloads"""
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, youtube_url, spotify_url, download_dir):
        super().__init__()
        self.youtube_url = youtube_url
        self.spotify_url = spotify_url
        self.download_dir = download_dir
        self.tasks = []
        self.completed = 0
        self.failed = 0
        self.current_task = None
        self.is_cancelled = False

    def get_ffmpeg_path(self):
        # Use platform utils for ffmpeg path
        return platform_utils.get_ffmpeg_path()

    def download_video(self, url, title):
        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    if total > 0:
                        percent = (downloaded / total) * 100
                        self.log.emit(f"Downloading {title}: {percent:.1f}%")
                except Exception:
                    pass  # Ignore progress calculation errors
            elif d['status'] == 'finished':
                self.log.emit(f"Download complete, converting {title} to MP3...")

        def clean_title(text):
            # Remove featuring artists and common accessories
            featuring_patterns = [
                r'\(feat\..*?\)',
                r'\(ft\..*?\)',
                r'\(featuring.*?\)',
                r'feat\..*?(?=[-\[]|$)',
                r'ft\..*?(?=[-\[]|$)',
                r'featuring.*?(?=[-\[]|$)',
                r'\(with.*?\)',
                r'\(prod\..*?\)',
                r'\(produced by.*?\)',
                r'\[.*?remix.*?\]',
                r'\(.*?remix.*?\)',
                r'\[.*?version.*?\]',
                r'\(.*?version.*?\)',
                r'\[official.*?\]',
                r'\(official.*?\)',
                r'\[lyrics.*?\]',
                r'\(lyrics.*?\)',
                r'\[audio.*?\]',
                r'\(audio.*?\)',
                r'\[official video.*?\]',
                r'\(official video.*?\)',
                r'\[music video.*?\]',
                r'\(music video.*?\)',
                r'\[hq\]',
                r'\(hq\)',
                r'\[hd\]',
                r'\(hd\)'
            ]
            
            import re
            # Apply all cleaning patterns
            cleaned = text
            for pattern in featuring_patterns:
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
            
            # Remove multiple spaces and trim
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            
            # Remove trailing hyphen or separator
            cleaned = re.sub(r'[-_]+$', '', cleaned).strip()
            
            return cleaned

        def extract_track_and_artist(title_text):
            # Try to split by " by " first (Spotify format)
            if " by " in title_text:
                track_name, artist_name = title_text.split(" by ", 1)
            else:
                # Try to split by " - " (common YouTube format)
                parts = title_text.split(" - ", 1)
                if len(parts) == 2:
                    artist_name, track_name = parts
                else:
                    # If no clear separation, treat entire title as track name
                    track_name = title_text
                    artist_name = "Unknown Artist"
            
            return clean_title(track_name), clean_title(artist_name)

        # Extract and clean track and artist names
        track_name, artist_name = extract_track_and_artist(title)
        
        # Create filename in [Track Name] - [Artist Name] format
        filename = f"{track_name} - {artist_name}"

        # Sanitize filename to remove invalid characters
        filename = "".join(c for c in filename if c.isalnum() or c in " -_()[]{}.,")
        filename = filename.strip()

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(self.download_dir, filename + '.%(ext)s'),
            'ffmpeg_location': self.get_ffmpeg_path(),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def get_youtube_tasks(self):
        tasks = []
        with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True}) as ydl:
            try:
                result = ydl.extract_info(self.youtube_url, download=False)
                if 'entries' in result:
                    for entry in result['entries']:
                        if entry:
                            video_url = entry.get('url')
                            title = entry.get('title', 'Untitled Video')
                            if video_url:
                                tasks.append({'query': video_url, 'title': title})
                elif result.get('url'):
                    tasks.append({
                        'query': result['url'],
                        'title': result.get('title', 'Untitled Video')
                    })
            except Exception as e:
                self.error.emit(f"Error extracting YouTube playlist: {str(e)}")
        return tasks

    def run(self):
        try:
            # Process YouTube playlist
            if self.youtube_url:
                try:
                    self.log.emit("Processing YouTube playlist...")
                    yt_tasks = self.get_youtube_tasks()
                    self.tasks.extend(yt_tasks)
                    self.log.emit(f"Found {len(yt_tasks)} tracks in YouTube playlist")
                except Exception as e:
                    self.error.emit(f"Error processing YouTube playlist: {str(e)}")

            # Process Spotify playlist
            if self.spotify_url:
                try:
                    self.log.emit("Processing Spotify playlist...")
                    spotify_tasks = spotify_handler.get_spotify_playlist_tracks(self.spotify_url)
                    for task in spotify_tasks:
                        if "://" not in task['query']:
                            task['query'] = "ytsearch1:" + task['query']
                    self.tasks.extend(spotify_tasks)
                    self.log.emit(f"Found {len(spotify_tasks)} tracks in Spotify playlist")
                except Exception as e:
                    self.error.emit(f"Error processing Spotify playlist: {str(e)}")

            total_tasks = len(self.tasks)
            if total_tasks == 0:
                self.error.emit("No tracks found to download")
                return

            # Process downloads
            for i, task in enumerate(self.tasks, 1):
                if self.is_cancelled:
                    self.log.emit("Download cancelled by user")
                    break

                self.current_task = task
                try:
                    self.log.emit(f"Starting download: {task['title']}")
                    self.download_video(task['query'], task['title'])
                    self.completed += 1
                    progress_percent = int((i / total_tasks) * 100)
                    self.progress.emit(progress_percent, 
                                     f"Processing {i}/{total_tasks}: {task['title']}")
                except Exception as e:
                    self.failed += 1
                    error_msg = str(e)
                    if "Video unavailable" in error_msg:
                        self.log.emit(f"Video unavailable: {task['title']}")
                    elif "Private video" in error_msg:
                        self.log.emit(f"Private video: {task['title']}")
                    else:
                        self.log.emit(f"Failed to download {task['title']}: {error_msg}")

            # Final status report
            if self.is_cancelled:
                self.finished.emit(f"Download cancelled. Completed: {self.completed}, Failed: {self.failed}")
            else:
                self.finished.emit(f"Download complete. Successfully downloaded {self.completed} of {total_tasks} tracks ({self.failed} failed)")
        
        except Exception as e:
            self.error.emit(f"An unexpected error occurred: {str(e)}")

    def cancel(self):
        self.is_cancelled = True
        self.log.emit("Cancelling download...")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Slim Thicc Command Center")
        self.setMinimumSize(800, 600)
        self.credentials_file = os.path.expanduser('~/.spotify_credentials.json')
        self.spotify_credentials = self.load_spotify_credentials()
        self.download_worker = None
        self.setup_styling()
        self.setup_ui()
        self.center_window()
        
        # Apply platform-specific GUI settings
        platform_utils.configure_gui_for_platform()

    def load_spotify_credentials(self):
        try:
            if os.path.exists(self.credentials_file):
                with open(self.credentials_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading credentials: {e}")
        return None

    def save_spotify_credentials(self, credentials):
        try:
            with open(self.credentials_file, 'w') as f:
                json.dump(credentials, f)
            os.chmod(self.credentials_file, 0o600)  # Set file permissions to user read/write only
        except Exception as e:
            print(f"Error saving credentials: {e}")

    def setup_spotify_credentials(self):
        dialog = SpotifyCredentialsDialog(self, self.spotify_credentials)
        if dialog.exec():
            credentials = dialog.get_credentials()
            if credentials['client_id'] and credentials['client_secret']:
                self.spotify_credentials = credentials
                self.save_spotify_credentials(credentials)
                # Set environment variables for the current session
                os.environ['SPOTIPY_CLIENT_ID'] = credentials['client_id']
                os.environ['SPOTIPY_CLIENT_SECRET'] = credentials['client_secret']
                return True
        return False

    def setup_styling(self):
        # Set the application style
        self.setStyleSheet("""
            * {
                font-family: "SF Pro Rounded", -apple-system, system-ui, BlinkMacSystemFont, sans-serif;
            }
            QMainWindow {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #ffffff;
                font-size: 16px;
            }
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                color: #ffffff;
                padding: 8px;
                font-size: 14px;
                selection-background-color: #1DB954;
            }
            QLineEdit:focus {
                border: 1px solid #1DB954;
            }
            QPushButton {
                background-color: #1DB954;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1ED760;
            }
            QPushButton:pressed {
                background-color: #1aa34a;
            }
            QPushButton:disabled {
                background-color: #4d4d4d;
            }
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #2d2d2d;
                text-align: center;
                color: white;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: #1DB954;
                border-radius: 4px;
            }
            QTextEdit {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                color: #ffffff;
                font-family: "SF Pro Rounded", "SF Mono", monospace;
                font-size: 18px;
                padding: 8px;
            }
            #title_label {
                font-size: 30px;
                font-weight: 700;
                color: #1DB954;
                padding: 20px;
            }
            QMessageBox {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QMessageBox QLabel {
                color: #ffffff;
                font-size: 18px;
            }
            QMessageBox QPushButton {
                min-width: 80px;
            }
        """)

    def setup_ui(self):
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # YouTube URL input
        youtube_label = QLabel("YouTube Playlist URL:")
        self.youtube_input = QLineEdit()
        self.youtube_input.setPlaceholderText("Enter YouTube playlist URL")
        
        # Spotify URL input
        spotify_label = QLabel("Spotify Playlist URL:")
        self.spotify_input = QLineEdit()
        self.spotify_input.setPlaceholderText("Enter Spotify playlist URL")
        
        # Download directory selection
        dir_layout = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select download directory")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_directory)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(browse_button)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat("%p% - %v of %m tasks")
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.start_download)
        self.download_button.setMinimumWidth(200)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_download)
        self.cancel_button.setMinimumWidth(200)
        self.cancel_button.setEnabled(False)
        
        self.spotify_setup_button = QPushButton("Setup Spotify")
        self.spotify_setup_button.clicked.connect(self.setup_spotify_credentials)
        self.spotify_setup_button.setMinimumWidth(200)
        
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.spotify_setup_button)
        button_layout.setAlignment(Qt.AlignCenter)
        
        # Add widgets to layout
        layout.addWidget(youtube_label)
        layout.addWidget(self.youtube_input)
        layout.addWidget(spotify_label)
        layout.addWidget(self.spotify_input)
        layout.addWidget(QLabel("Download Directory:"))
        layout.addLayout(dir_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_text)
        layout.addLayout(button_layout)
        
        # Center the window
        self.center_window()
        
    def center_window(self):
        # Center window on screen, with special handling for Raspberry Pi
        if platform_utils.is_raspberry_pi():
            # On Raspberry Pi, maximize the window for better touchscreen usage
            self.showMaximized()
        else:
            # Regular window centering for other platforms
            screen_geometry = QApplication.primaryScreen().geometry()
            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2
            self.move(x, y)
        
    def cancel_download(self):
        if hasattr(self, 'worker') and self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.download_button.setEnabled(True)
            self.spotify_setup_button.setEnabled(True)
            
    def start_download(self):
        youtube_url = self.youtube_input.text().strip()
        spotify_url = self.spotify_input.text().strip()
        download_dir = self.dir_input.text().strip()
        
        if not youtube_url and not spotify_url:
            QMessageBox.warning(self, "Error", "Please enter at least one playlist URL")
            return
            
        if not download_dir:
            QMessageBox.warning(self, "Error", "Please select a download directory")
            return
            
        if spotify_url and not os.getenv("SPOTIPY_CLIENT_ID"):
            if not self.setup_spotify_credentials():
                QMessageBox.warning(self, "Error", "Spotify credentials are required for Spotify playlists")
                return
                
        # Clear previous log
        self.log_text.clear()
        self.progress_bar.setValue(0)
        
        # Create and start worker thread
        self.worker = DownloadWorker(youtube_url, spotify_url, download_dir)
        self.worker.progress.connect(self.update_progress)
        self.worker.log.connect(self.log_message)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(self.download_finished)
        
        # Update UI state
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.spotify_setup_button.setEnabled(False)
        
        # Start the worker
        self.worker.start()
        
    def download_finished(self, message):
        self.log_message(message)
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.spotify_setup_button.setEnabled(True)
        self.worker = None

    def browse_directory(self):
        # Use platform-specific default directory
        default_dir = platform_utils.get_app_data_dir()
        directory = QFileDialog.getExistingDirectory(self, "Select Download Directory", default_dir)
        if directory:  # Only update if a directory was selected
            self.dir_input.setText(directory)

    def log_message(self, message):
        self.log_text.append(message)

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.log_text.append(message)

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)
        self.download_button.setEnabled(True)

def main():
    app = QApplication(sys.argv)
    
    # Set application-wide attributes
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 