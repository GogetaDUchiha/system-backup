import os
import tarfile
import json
import time
import requests
from datetime import datetime
from glob import glob
import threading
import schedule
import logging

# --- Constants ---
SERVER_URL = "http://127.0.0.1:5000"
# Changed BACKUP_DIR to user's home directory for better practice
BACKUP_DIR = os.path.join(os.path.expanduser("~"), "BackupSystemBackups") 
CONFIG_FILE = os.path.join(BACKUP_DIR, "backup_config.json")
LOG_FILE = os.path.join(BACKUP_DIR, "backup.log")
EXCLUDE_DIRS = ["/tmp", "/proc", "/run", "/sys", "/dev", "/mnt", "/media", BACKUP_DIR, "/var/log", "/var/tmp"]
FILE_SIZE_LIMIT = 500 * 1024 * 1024  # 500 MB

DEFAULT_CONFIG = {
    "auto_backup_enabled": False,
    "backup_type": "specific",  # Options: "full", "specific"
    "specific_dir": os.path.expanduser("~"), # Default to user home directory
    "frequency": "daily",       # Options: "daily", "weekly", "monthly"
    "time": "00:00",            # Time format: HH:MM (24-hour)
}

# Ensure directories exist
os.makedirs(BACKUP_DIR, exist_ok=True)

# --- Logging Setup (for internal Client.py logging, separate from GUI log) ---
# This logger is for Client.py's own internal records, not directly for the GUI.
# GUI receives messages via log_callback.
client_logger = logging.getLogger(__name__)
client_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(LOG_FILE)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
# Ensure only one file handler is added to avoid duplicate logs
if not client_logger.handlers:
    client_logger.addHandler(file_handler)

# --- Helper for sending messages to GUI and internal log ---
def _log(message, level="INFO", log_callback=None):
    """Logs a message internally and sends it to the GUI via callback."""
    if level == "INFO":
        client_logger.info(message)
    elif level == "WARNING":
        client_logger.warning(message)
    elif level == "ERROR":
        client_logger.error(message)
    else:
        client_logger.debug(message) # Default for other levels

    if log_callback and callable(log_callback):
        log_callback(message, level)

# ------------------------
# Configuration Functions
# ------------------------

def save_config(config, log_callback=None):
    """Save the backup configuration to a JSON file."""
    try:
        with open(CONFIG_FILE, "w") as file:
            json.dump(config, file, indent=4)
        _log("Configuration saved successfully.", "INFO", log_callback)
        return True, "Configuration saved successfully."
    except Exception as e:
        _log(f"Failed to save configuration: {e}", "ERROR", log_callback)
        return False, f"Failed to save configuration: {e}"

def load_config(log_callback=None):
    """Load the backup configuration from a JSON file."""
    if not os.path.exists(CONFIG_FILE):
        _log("Config file not found. Creating with default settings.", "INFO", log_callback)
        save_config(DEFAULT_CONFIG, log_callback)
    try:
        with open(CONFIG_FILE, "r") as file:
            return json.load(file)
    except json.JSONDecodeError as e:
        _log(f"Error reading config file (JSON format issue): {e}. Using default config.", "ERROR", log_callback)
        return DEFAULT_CONFIG
    except Exception as e:
        _log(f"Failed to load configuration: {e}. Using default config.", "ERROR", log_callback)
        return DEFAULT_CONFIG

# Removed configure_auto_backup as this is handled by GUI

# ------------------------
# Latency Measurement (internal, not directly used by GUI)
# ------------------------

def measure_latency(start_time, end_time, operation, log_callback=None):
    """Calculate and display latency for upload/download."""
    latency = end_time - start_time
    _log(f"{operation} completed in {latency:.2f} seconds.", "INFO", log_callback)


# ------------------------
# Backup Functions
# ------------------------

def scan_directory(path, log_callback=None):
    """Scan a directory and return counts of directories, files, and total size."""
    dir_count, file_count, total_size = 0, 0, 0
    # Use a set for faster lookup of excluded paths
    excluded_normalized_paths = {os.path.normpath(d) for d in EXCLUDE_DIRS}

    for root, dirs, files in os.walk(path, followlinks=False): # Added followlinks=False to prevent infinite loops
        # Filter out excluded directories to not count them and prevent traversing into them
        dirs[:] = [d for d in dirs if not os.path.normpath(os.path.join(root, d)) in excluded_normalized_paths and \
                   not any(os.path.normpath(os.path.join(root, d)).startswith(excluded) for excluded in excluded_normalized_paths)]
        
        dir_count += len(dirs)
        
        for f in files:
            file_path = os.path.join(root, f)
            if os.path.exists(file_path):
                # Check if the file's path is within an excluded directory
                if any(os.path.normpath(file_path).startswith(excluded) for excluded in excluded_normalized_paths):
                    _log(f"DEBUG: Skipping file in excluded path: {file_path}", "DEBUG", log_callback)
                    continue

                try:
                    file_size = os.path.getsize(file_path)
                    file_count += 1
                    total_size += file_size
                except OSError as e:
                    _log(f"WARNING: Could not get size of {file_path}: {e}", "WARNING", log_callback)
    return dir_count, file_count, total_size

def create_tarball_with_progress(source_path, dest_path, exclude_dirs=None, log_callback=None):
    """Create a tar.gz archive with progress updates and error handling."""
    exclude_dirs = exclude_dirs or []
    # Normalize exclude paths for robust checking
    excluded_normalized_paths = {os.path.normpath(d) for d in exclude_dirs}

    try:
        _log(f"Starting tarball creation for {source_path}.", "INFO", log_callback)

        total_dirs, total_files, _ = scan_directory(source_path, log_callback)
        processed_dirs, processed_files = 0, 0
        
        # Use a temporary file for tarball creation to prevent partial uploads on failure
        temp_dest_path = dest_path + ".tmp"

        with tarfile.open(temp_dest_path, "w:gz") as tar:
            for root, dirs, files in os.walk(source_path, followlinks=False): # Added followlinks=False
                current_normalized_root = os.path.normpath(root)

                # Filter out excluded directories from traversal
                # Important: Modify dirs in-place to prune the walk
                dirs[:] = [d for d in dirs if not os.path.normpath(os.path.join(root, d)) in excluded_normalized_paths and \
                           not any(os.path.normpath(os.path.join(root, d)).startswith(excluded) for excluded in excluded_normalized_paths)]

                # Add directories to tarball
                for directory in dirs:
                    dir_path = os.path.join(root, directory)
                    normalized_dir_path = os.path.normpath(dir_path)
                    if normalized_dir_path in excluded_normalized_paths or any(normalized_dir_path.startswith(excluded) for excluded in excluded_normalized_paths):
                        _log(f"DEBUG: Skipping explicitly excluded directory: {dir_path}", "DEBUG", log_callback)
                        continue
                    if not os.access(dir_path, os.R_OK):
                        _log(f"WARNING: Skipping unreadable directory: {dir_path}", "WARNING", log_callback)
                        continue
                    try:
                        tar.add(dir_path, arcname=os.path.relpath(dir_path, source_path))
                        processed_dirs += 1
                        _log(f"PROGRESS: Processed {processed_dirs}/{total_dirs} directories in {source_path}", "INFO", log_callback)
                    except Exception as e:
                        _log(f"WARNING: Failed to add directory {dir_path} to tarball: {e}", "WARNING", log_callback)

                # Add files to tarball
                for file in files:
                    file_path = os.path.join(root, file)
                    normalized_file_path = os.path.normpath(file_path)

                    # Check if the file is in an excluded directory
                    if normalized_file_path in excluded_normalized_paths or any(normalized_file_path.startswith(excluded) for excluded in excluded_normalized_paths):
                        _log(f"DEBUG: Skipping explicitly excluded file: {file_path}", "DEBUG", log_callback)
                        continue

                    if not os.access(file_path, os.R_OK):
                        _log(f"WARNING: Skipping unreadable file: {file_path}", "WARNING", log_callback)
                        continue
                    
                    try:
                        file_size = os.path.getsize(file_path)
                        if file_size > FILE_SIZE_LIMIT:
                            _log(f"WARNING: Skipping large file: {file_path} (> {FILE_SIZE_LIMIT / (1024 * 1024)} MB)", "WARNING", log_callback)
                            continue
                    except OSError as e:
                        _log(f"WARNING: Could not get size of {file_path}, skipping: {e}", "WARNING", log_callback)
                        continue

                    try:
                        tar.add(file_path, arcname=os.path.relpath(file_path, source_path))
                        processed_files += 1
                        _log(f"PROGRESS: Processed {processed_files}/{total_files} files in {source_path}", "INFO", log_callback)
                    except Exception as e:
                        _log(f"WARNING: Failed to add file {file_path} to tarball: {e}", "WARNING", log_callback)
        
        os.rename(temp_dest_path, dest_path) # Atomically move temp file to final destination
        _log(f"Tarball created successfully: {dest_path}", "INFO", log_callback)
        return True, f"Tarball created at {dest_path}"
    except tarfile.TarError as e:
        _log(f"Tarball creation error: {e}", "ERROR", log_callback)
        return False, f"Tarball creation error: {e}"
    except Exception as e:
        _log(f"Failed to create tarball: {e}", "ERROR", log_callback)
        return False, f"Failed to create tarball: {e}"
    finally:
        # Clean up temp file if it exists due to an error during creation
        if os.path.exists(temp_dest_path):
            os.remove(temp_dest_path)
            _log(f"Cleaned up temporary file: {temp_dest_path}", "INFO", log_callback)


def full_system_backup(log_callback=None):
    """Perform a full system backup."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"full_system_{timestamp}.tar.gz"
        backup_path = os.path.join(BACKUP_DIR, backup_name)

        _log("Starting full system backup.", "INFO", log_callback)
        success, message = create_tarball_with_progress("/", backup_path, exclude_dirs=EXCLUDE_DIRS, log_callback=log_callback)
        if success:
            _log(f"Full system backup completed: {backup_path}", "INFO", log_callback)
            return True, f"Full system backup completed to {backup_path}"
        else:
            _log(f"Full system backup failed: {message}", "ERROR", log_callback)
            return False, f"Full system backup failed: {message}"
    except Exception as e:
        _log(f"Full system backup failed: {e}", "ERROR", log_callback)
        return False, f"Full system backup failed: {e}"

def specific_directory_backup(directory, log_callback=None):
    """Perform a backup of a specific directory."""
    if not os.path.exists(directory):
        _log(f"Directory does not exist: {directory}", "ERROR", log_callback)
        return False, f"Directory does not exist: {directory}"
    
    backup_name = f"{os.path.basename(directory)}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    _log(f"Starting backup for specific directory: {directory}", "INFO", log_callback)
    success, message = create_tarball_with_progress(directory, backup_path, log_callback=log_callback)
    
    if success:
        _log(f"Specific directory backup completed: {backup_path}", "INFO", log_callback)
        return True, f"Specific directory backup completed to {backup_path}"
    else:
        _log(f"Specific directory backup failed: {message}", "ERROR", log_callback)
        return False, f"Specific directory backup failed: {message}"
            
def restore_backup(backup_file, restore_path, log_callback=None):
    """Restore a backup from a tar.gz file."""
    if not os.path.exists(backup_file):
        _log(f"Backup file not found: {backup_file}", "ERROR", log_callback)
        return False, "Backup file not found."
    # Ensure restore_path exists, create if not
    if not os.path.isdir(restore_path):
        try:
            os.makedirs(restore_path, exist_ok=True)
            _log(f"Created restore directory: {restore_path}", "INFO", log_callback)
        except OSError as e:
            _log(f"Failed to create restore directory {restore_path}: {e}", "ERROR", log_callback)
            return False, f"Failed to create restore directory: {e}"

    try:
        _log(f"Restoring backup: {backup_file} to {restore_path}", "INFO", log_callback)
        with tarfile.open(backup_file, "r:gz") as tar:
            # You could add progress here by iterating through members
            members = tar.getmembers()
            total_members = len(members)
            for i, member in enumerate(members):
                try:
                    tar.extract(member, restore_path)
                    # _log(f"PROGRESS: Extracted {member.name} ({i+1}/{total_members})", "DEBUG", log_callback) # Detailed but verbose
                except Exception as e:
                    _log(f"WARNING: Failed to extract {member.name}: {e}", "WARNING", log_callback)

        _log("Restore completed successfully.", "INFO", log_callback)
        return True, "Restore completed successfully."
    except tarfile.TarError as e:
        _log(f"Restore failed (TarError): {e}", "ERROR", log_callback)
        return False, f"Restore failed (TarError): {e}"
    except Exception as e:
        _log(f"Failed to restore backup: {e}", "ERROR", log_callback)
        return False, f"Failed to restore backup: {e}"

# ------------------------
# Network Functions (renamed to _headless and accept log_callback)
# ------------------------

def upload_backup_headless(home_directory, file_path, log_callback=None):
    """Upload a backup to the server with latency measurement."""
    if not file_path or not os.path.exists(file_path):
        _log(f"Invalid file path for upload: {file_path}", "ERROR", log_callback)
        return False, "Invalid file path for upload."

    try:
        start_time = time.time()
        with open(file_path, "rb") as file:
            response = requests.post(
                f"{SERVER_URL}/upload",
                files={"file": file},
                data={"home_directory": home_directory}
            )
        end_time = time.time()
        
        if response.status_code == 200:
            measure_latency(start_time, end_time, "Upload", log_callback)
            _log(f"Backup uploaded successfully: {response.json().get('message', 'Success')}", "INFO", log_callback)
            return True, response.json().get('message', 'Success')
        else:
            error_message = response.text
            _log(f"Failed to upload backup: {error_message}", "ERROR", log_callback)
            return False, f"Failed to upload backup: {error_message}"
    except requests.exceptions.ConnectionError as e:
        _log(f"Server connection failed for upload: {e}", "ERROR", log_callback)
        return False, f"Server connection failed: {e}"
    except Exception as e:
        _log(f"Upload failed: {e}", "ERROR", log_callback)
        return False, f"Upload failed: {e}"

def download_backup_headless(home_directory, filename, destination_path, log_callback=None):
    """Download a backup from the server with latency measurement."""
    if not filename:
        _log("No filename provided for download.", "WARNING", log_callback)
        return False, "No filename provided."
    if not os.path.isdir(destination_path):
        _log(f"Download destination is not a valid directory: {destination_path}", "ERROR", log_callback)
        return False, "Download destination is not a valid directory."

    try:
        start_time = time.time()
        response = requests.post(f"{SERVER_URL}/download", json={"filename": filename, "home_directory": home_directory})
        end_time = time.time()
        
        if response.status_code == 200:
            download_file_path = os.path.join(destination_path, filename)
            with open(download_file_path, "wb") as f:
                f.write(response.content)
            measure_latency(start_time, end_time, "Download", log_callback)
            _log(f"Backup downloaded to: {download_file_path}", "INFO", log_callback)
            return True, f"Backup downloaded to {download_file_path}"
        else:
            error_message = response.json().get('error', response.text)
            _log(f"Failed to download backup: {error_message}", "ERROR", log_callback)
            return False, f"Failed to download backup: {error_message}"
    except requests.exceptions.ConnectionError as e:
        _log(f"Server connection failed for download: {e}", "ERROR", log_callback)
        return False, f"Server connection failed: {e}"
    except Exception as e:
        _log(f"Download failed: {e}", "ERROR", log_callback)
        return False, f"Download failed: {e}"

# ------------------------
# Server Interaction Functions (renamed to _headless and accept log_callback)
# ------------------------

def authenticate_user_headless(username, password, log_callback=None):
    """Authenticate the user with the server."""
    try:
        _log(f"Attempting to authenticate user: {username}", "INFO", log_callback)
        response = requests.post(f"{SERVER_URL}/authenticate", json={"username": username, "password": password})
        if response.status_code == 200:
            home_directory = response.json()["home_directory"]
            _log("Authentication successful.", "INFO", log_callback)
            return home_directory, None # Return home_directory and no error
        else:
            error_message = response.json().get("error", "Authentication failed!")
            _log(f"Authentication failed: {error_message}", "ERROR", log_callback)
            return None, error_message # Return None for home_directory and an error message
    except requests.exceptions.ConnectionError as e:
        _log(f"Server connection failed during authentication: {e}", "ERROR", log_callback)
        return None, f"Server connection failed: {e}. Is the server running?"
    except Exception as e:
        _log(f"Authentication process failed: {e}", "ERROR", log_callback)
        return None, f"Authentication process failed: {e}"

def list_local_backups_headless(log_callback=None):
    """Lists all local backups."""
    files = glob(os.path.join(BACKUP_DIR, "*.tar.gz"))
    if not files:
        _log("No local backups available.", "INFO", log_callback)
        return []
    
    # Return just the filenames for GUI listbox
    file_names = [os.path.basename(f) for f in files]
    _log(f"Found {len(file_names)} local backup(s).", "INFO", log_callback)
    return file_names

def delete_local_backup_headless(filename, log_callback=None):
    """Deletes a local backup file."""
    file_path_to_delete = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(file_path_to_delete):
        _log(f"Local backup file not found: {filename}", "ERROR", log_callback)
        return False, "File not found."
    
    try:
        os.remove(file_path_to_delete)
        _log(f"Deleted local backup: {filename}", "INFO", log_callback)
        return True, "Local backup deleted successfully."
    except Exception as e:
        _log(f"Failed to delete local backup {filename}: {e}", "ERROR", log_callback)
        return False, f"Failed to delete: {e}"

def list_server_backups_headless(home_directory, log_callback=None):
    """Lists backups stored on the server."""
    try:
        _log("Requesting server backup list...", "INFO", log_callback)
        response = requests.post(f"{SERVER_URL}/list", json={"home_directory": home_directory})
        if response.status_code == 200:
            files = response.json().get("files", [])
            if not files:
                _log("No server backups available.", "INFO", log_callback)
                return [], None # Return empty list, no error
            else:
                _log(f"Found {len(files)} server backups.", "INFO", log_callback)
                return files, None # Return list of files, no error
        else:
            error_message = response.json().get("error", "Failed to list server backups.")
            _log(f"Failed to list server backups: {error_message}", "ERROR", log_callback)
            return None, error_message # Return None for files, and an error message
    except requests.exceptions.ConnectionError as e:
        _log(f"Server connection failed when listing backups: {e}", "ERROR", log_callback)
        return None, f"Server connection failed: {e}. Is the server running?"
    except Exception as e:
        _log(f"Failed to list server backups: {e}", "ERROR", log_callback)
        return None, f"Failed to list server backups: {e}"

def delete_server_backup_headless(home_directory, filename, log_callback=None):
    """Deletes a backup stored on the server."""
    if not filename:
        _log("No filename provided for server deletion.", "WARNING", log_callback)
        return False, "No filename provided."

    try:
        _log(f"Attempting to delete {filename} from server...", "INFO", log_callback)
        response = requests.post(f"{SERVER_URL}/delete", json={"filename": filename, "home_directory": home_directory})
        if response.status_code == 200:
            _log(f"Deleted server backup: {filename}", "INFO", log_callback)
            return True, "Server backup deleted successfully."
        else:
            error_message = response.json().get("error", "Failed to delete server backup.")
            _log(f"Failed to delete server backup: {error_message}", "ERROR", log_callback)
            return False, f"Failed to delete server backup: {error_message}"
    except requests.exceptions.ConnectionError as e:
        _log(f"Server connection failed when deleting backup: {e}", "ERROR", log_callback)
        return False, f"Server connection failed: {e}"
    except Exception as e:
        _log(f"Failed to delete server backup: {e}", "ERROR", log_callback)
        return False, f"Failed to delete server backup: {e}"

# ------------------------
# Auto-Backup Scheduler (now accepts log_callback)
# ------------------------

# Global variable to hold the scheduler thread, so it can be managed (stopped/restarted)
_scheduler_thread = None
_stop_scheduler_event = threading.Event()

def _run_scheduler(log_callback):
    """Runs the schedule continuously in a separate thread."""
    while not _stop_scheduler_event.is_set():
        schedule.run_pending()
        time.sleep(1) # Check every second

def auto_backup_scheduler(log_callback=None):
    """
    Schedules and executes auto-backups based on configuration.
    This function will stop any existing scheduler thread and start a new one
    to apply updated configurations.
    """
    global _scheduler_thread, _stop_scheduler_event

    # Stop any running scheduler first
    if _scheduler_thread and _scheduler_thread.is_alive():
        _log("Stopping existing auto-backup scheduler thread...", "INFO", log_callback)
        _stop_scheduler_event.set() # Signal the old thread to stop
        _scheduler_thread.join(timeout=5) # Wait for it to finish, with a timeout
        if _scheduler_thread.is_alive():
            _log("WARNING: Old scheduler thread did not terminate cleanly within 5 seconds.", "WARNING", log_callback)
        else:
            _log("Existing auto-backup scheduler thread stopped successfully.", "INFO", log_callback)
    
    # Reset the stop event for the new thread
    _stop_scheduler_event.clear()

    config = load_config(log_callback)
    
    # Clear existing jobs to prevent duplicates when restarting
    schedule.clear()

    if not config.get("auto_backup_enabled", False):
        _log("Auto-backup is currently disabled in configuration. Scheduler not started.", "INFO", log_callback)
        return False # Indicate scheduler is not active

    backup_type = config.get("backup_type")
    specific_dir = config.get("specific_dir")
    frequency = config.get("frequency")
    backup_time = config.get("time")

    # Validate config
    if backup_type not in ["full", "specific"]:
        _log(f"Invalid backup_type in config: '{backup_type}'. Must be 'full' or 'specific'.", "ERROR", log_callback)
        return False
    if backup_type == "specific" and (not specific_dir or not os.path.isdir(specific_dir)):
        _log(f"Specific directory '{specific_dir}' does not exist or is invalid for specific backup.", "ERROR", log_callback)
        return False
    if frequency not in ["daily", "weekly", "monthly"]:
        _log(f"Invalid frequency in config: '{frequency}'. Must be 'daily', 'weekly', or 'monthly'.", "ERROR", log_callback)
        return False
    try:
        time.strptime(backup_time, "%H:%M")
    except ValueError:
        _log(f"Invalid time format in config: '{backup_time}'. Expected HH:MM (e.g., 00:00).", "ERROR", log_callback)
        return False

    def scheduled_backup_task():
        """The actual task executed by the scheduler."""
        _log("Running scheduled auto-backup task...", "INFO", log_callback)
        if backup_type == "full":
            success, msg = full_system_backup(log_callback=log_callback)
        elif backup_type == "specific":
            success, msg = specific_directory_backup(specific_dir, log_callback=log_callback)
        
        if success:
            _log(f"Scheduled auto-backup task finished successfully: {msg}", "SUCCESS", log_callback)
        else:
            _log(f"Scheduled auto-backup task failed: {msg}", "ERROR", log_callback)

    # Schedule the job based on frequency
    if frequency == "daily":
        schedule.every().day.at(backup_time).do(scheduled_backup_task)
        _log(f"Auto-backup scheduled: Daily at {backup_time} ({backup_type} backup).", "INFO", log_callback)
    elif frequency == "weekly":
        # For simplicity, schedule for Sunday. You might want to let the user pick a day.
        schedule.every().sunday.at(backup_time).do(scheduled_backup_task)
        _log(f"Auto-backup scheduled: Weekly (Sunday) at {backup_time} ({backup_type} backup).", "INFO", log_callback)
    elif frequency == "monthly":
        # Schedule for the 1st of every month. Schedule library doesn't have direct monthly.
        # This is a workaround, might not be exact for monthly.
        # A more robust solution might involve checking the date within the task or using cron-like logic.
        _log("WARNING: Monthly scheduling is approximated to the 1st day of the month.", "WARNING", log_callback)
        schedule.every().day.at(backup_time).do(lambda: datetime.now().day == 1 and scheduled_backup_task())
        _log(f"Auto-backup scheduled: Monthly (1st day) at {backup_time} ({backup_type} backup).", "INFO", log_callback)
    
    # Start the scheduler thread if not already running
    if not (_scheduler_thread and _scheduler_thread.is_alive()):
        _scheduler_thread = threading.Thread(target=_run_scheduler, args=(log_callback,), daemon=True)
        _scheduler_thread.start()
        _log("Auto-backup scheduler thread started.", "INFO", log_callback)
        return True # Indicate scheduler is active
    else:
        _log("Auto-backup scheduler already running (or restarted internally).", "INFO", log_callback)
        return True