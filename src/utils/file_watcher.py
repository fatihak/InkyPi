"""
File Watcher for Live Reload

Watches for changes in plugin files and triggers reload events.
"""

import os
import time
import logging
from typing import Set, Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

logger = logging.getLogger(__name__)


class PluginFileWatcher(FileSystemEventHandler):
    """Watches for changes in plugin files."""
    
    def __init__(self, callback: Callable[[str], None], debounce_seconds: float = 0.5):
        """
        Initialize the file watcher.
        
        Args:
            callback: Function to call when a file changes (receives file path)
            debounce_seconds: Minimum time between callback calls
        """
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.last_callback_time = 0
        self.pending_files: Set[str] = set()
        
    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
            
        # Only watch relevant file types
        file_path = event.src_path
        if not self._is_relevant_file(file_path):
            return
            
        # Add to pending files
        self.pending_files.add(file_path)
        
        # Debounce rapid changes
        current_time = time.time()
        if current_time - self.last_callback_time >= self.debounce_seconds:
            self._process_pending_changes()
            self.last_callback_time = current_time
        else:
            # Schedule processing after debounce period
            if hasattr(self, '_debounce_timer'):
                self._debounce_timer.cancel()
            
            import threading
            self._debounce_timer = threading.Timer(
                self.debounce_seconds, 
                self._process_pending_changes
            )
            self._debounce_timer.start()
    
    def _is_relevant_file(self, file_path: str) -> bool:
        """Check if file is relevant for live reload."""
        # Check file extension
        relevant_extensions = {'.py', '.html', '.css', '.js', '.json', '.yaml', '.yml'}
        if not any(file_path.endswith(ext) for ext in relevant_extensions):
            return False
            
        # Check if file is in a plugin directory or templates
        abs_path = os.path.abspath(file_path)
        
        # Plugin source files
        if '/src/plugins/' in abs_path:
            return True
            
        # Template files
        if '/src/templates/' in abs_path:
            return True
            
        # Configuration files
        if '/src/config/' in abs_path:
            return True
            
        return False
    
    def _process_pending_changes(self):
        """Process all pending file changes."""
        if not self.pending_files:
            return
            
        # Get the most recently changed file
        changed_files = list(self.pending_files)
        self.pending_files.clear()
        
        # Call callback for each changed file
        for file_path in changed_files:
            try:
                logger.info(f"File changed: {file_path}")
                self.callback(file_path)
            except Exception as e:
                logger.error(f"Error processing file change {file_path}: {e}")


class LiveReloadManager:
    """Manages file watching for live reload functionality."""
    
    def __init__(self, socketio_instance):
        """
        Initialize the live reload manager.
        
        Args:
            socketio_instance: Flask-SocketIO instance for broadcasting changes
        """
        self.socketio = socketio_instance
        self.observer: Optional[Observer] = None
        self.is_watching = False
        
    def start_watching(self, watch_paths=None):
        """
        Start watching for file changes.
        
        Args:
            watch_paths: List of paths to watch (defaults to common plugin paths)
        """
        if self.is_watching:
            logger.warning("File watcher already running")
            return
            
        if watch_paths is None:
            watch_paths = [
                'src/plugins',
                'src/templates', 
                'src/config'
            ]
        
        # Create event handler
        def on_file_changed(file_path: str):
            """Handle file change event."""
            logger.info(f"Broadcasting reload signal for: {file_path}")
            self.socketio.emit('reload', {
                'file': file_path,
                'timestamp': time.time()
            })
        
        handler = PluginFileWatcher(on_file_changed)
        
        # Set up observer
        self.observer = Observer()
        
        # Watch each path
        watched_any = False
        for watch_path in watch_paths:
            if os.path.exists(watch_path):
                self.observer.schedule(handler, watch_path, recursive=True)
                logger.info(f"Watching path: {watch_path}")
                watched_any = True
            else:
                logger.warning(f"Watch path does not exist: {watch_path}")
        
        # Start observing only if we have valid paths
        if watched_any:
            self.observer.start()
            self.is_watching = True
            logger.info("File watcher started for live reload")
        else:
            self.observer = None
            logger.warning("No valid paths to watch, file watcher not started")
    
    def stop_watching(self):
        """Stop watching for file changes."""
        if not self.is_watching:
            return
            
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            
        self.is_watching = False
        logger.info("File watcher stopped")
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        self.stop_watching()