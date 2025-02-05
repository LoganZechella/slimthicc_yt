import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QGridLayout, QLabel, QLineEdit, 
                            QPushButton, QProgressBar, QTextEdit, QFileDialog,
                            QFrame, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon
import yt_dlp
import platform
import spotify_handler

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

    def get_ffmpeg_path(self):
        base_path = os.path.dirname(os.path.abspath(__file__))
        if platform.machine() == 'arm64':
            return os.path.join(base_path, 'ffmpeg_bin', 'arm64', 'ffmpeg')
        return os.path.join(base_path, 'ffmpeg_bin', 'x86_64', 'ffmpeg')

    def download_video(self, url):
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(self.download_dir, '%(title)s.%(ext)s'),
            'ffmpeg_location': self.get_ffmpeg_path(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def get_youtube_tasks(self):
        tasks = []
        with yt_dlp.YoutubeDL({'extract_flat': True}) as ydl:
            result = ydl.extract_info(self.youtube_url, download=False)
            if 'entries' in result:
                for entry in result['entries']:
                    video_url = entry.get('url')
                    title = entry.get('title', 'Untitled Video')
                    tasks.append({'query': video_url, 'title': title})
        return tasks

    def run(self):
        try:
            # Process YouTube playlist
            if self.youtube_url:
                try:
                    yt_tasks = self.get_youtube_tasks()
                    self.tasks.extend(yt_tasks)
                    self.log.emit(f"Found {len(yt_tasks)} tracks in YouTube playlist")
                except Exception as e:
                    self.error.emit(f"Error processing YouTube playlist: {str(e)}")

            # Process Spotify playlist
            if self.spotify_url:
                try:
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
                try:
                    self.log.emit(f"Downloading: {task['title']}")
                    self.download_video(task['query'])
                    self.completed += 1
                    progress_percent = int((i / total_tasks) * 100)
                    self.progress.emit(progress_percent, 
                                     f"Processing {i}/{total_tasks}: {task['title']}")
                except Exception as e:
                    self.log.emit(f"Failed to download {task['title']}: {str(e)}")

            self.finished.emit(f"Downloaded {self.completed} of {total_tasks} tracks successfully")
        except Exception as e:
            self.error.emit(f"An error occurred: {str(e)}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Playlist Downloader")
        self.setMinimumSize(1000, 800)
        self.setup_ui()
        self.setup_styling()

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
        layout.setContentsMargins(30, 10, 30, 30)

        # Title
        title_label = QLabel("DJ Slim Thicc Command Center")
        title_label.setObjectName("title_label")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Form layout for inputs
        form_layout = QGridLayout()
        form_layout.setSpacing(15)

        # YouTube URL
        youtube_label = QLabel("YouTube Playlist URL:")
        self.youtube_input = QLineEdit()
        self.youtube_input.setPlaceholderText("Enter YouTube playlist URL...")
        form_layout.addWidget(youtube_label, 0, 0)
        form_layout.addWidget(self.youtube_input, 0, 1)

        # Spotify URL
        spotify_label = QLabel("Spotify Playlist URL:")
        self.spotify_input = QLineEdit()
        self.spotify_input.setPlaceholderText("Enter Spotify playlist URL...")
        form_layout.addWidget(spotify_label, 1, 0)
        form_layout.addWidget(self.spotify_input, 1, 1)

        # Download Directory
        dir_label = QLabel("Download Location:")
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select download location...")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_directory)
        form_layout.addWidget(dir_label, 2, 0)
        form_layout.addWidget(self.dir_input, 2, 1)
        form_layout.addWidget(browse_button, 2, 2)

        layout.addLayout(form_layout)

        # Progress section
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(30)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready to start download...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Log section
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        layout.addWidget(self.log_text)

        # Download button
        self.download_button = QPushButton("Start Download")
        self.download_button.setFixedWidth(200)
        self.download_button.clicked.connect(self.start_download)
        
        # Center the download button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.download_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

    def browse_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Download Directory",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly
        )
        if dir_path:
            self.dir_input.setText(dir_path)

    def log_message(self, message):
        self.log_text.append(message)

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)
        self.download_button.setEnabled(True)

    def download_finished(self, message):
        self.log_message(message)
        QMessageBox.information(self, "Download Complete", message)
        self.download_button.setEnabled(True)

    def start_download(self):
        youtube_url = self.youtube_input.text().strip()
        spotify_url = self.spotify_input.text().strip()
        download_dir = self.dir_input.text().strip()

        if not (youtube_url or spotify_url):
            QMessageBox.warning(self, "Error", 
                              "Please enter at least one playlist URL (YouTube or Spotify).")
            return

        if not download_dir:
            QMessageBox.warning(self, "Error", "Please select a download directory.")
            return

        # Create download directory if it doesn't exist
        os.makedirs(download_dir, exist_ok=True)

        # Disable the download button
        self.download_button.setEnabled(False)

        # Reset progress
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self.log_message("Starting download process...")

        # Create and start the worker thread
        self.worker = DownloadWorker(youtube_url, spotify_url, download_dir)
        self.worker.progress.connect(self.update_progress)
        self.worker.log.connect(self.log_message)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(self.download_finished)
        self.worker.start()

def main():
    app = QApplication(sys.argv)
    
    # Set application-wide attributes
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 