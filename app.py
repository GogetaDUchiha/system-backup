import dearpygui.dearpygui as dpg # Corrected import
import sys
import os
import threading
import json
import time

# Correctly add the parent directory of Client to the Python path
# Assuming app.py is in project/backup and Client.py is in project/backup/Client
sys.path.append(os.path.join(os.path.dirname(__file__), 'Client'))

from Client.Client import (
    authenticate_user_headless,
    full_system_backup,
    specific_directory_backup,
    restore_backup,
    list_local_backups_headless,
    delete_local_backup_headless,
    upload_backup_headless,
    download_backup_headless,
    list_server_backups_headless,
    delete_server_backup_headless,
    load_config,
    save_config,
    auto_backup_scheduler # Import the scheduler function
)

# --- GUI Variables ---
logged_in_user = None
home_directory = None
auto_backup_scheduler_thread = None # To hold the scheduler thread

# --- Constants for Styling ---
ITEM_WIDTH = 300 # Standard width for input fields and listboxes
BUTTON_HEIGHT = 25 # Standard height for buttons
LISTBOX_VISIBLE_ITEMS = 5 # Number of items visible in listboxes without scrolling
GROUP_SPACING = 15 # Spacing between logical groups of widgets

# --- Log Messages ---
def log_message(message, level="INFO"):
    """Appends a message to the GUI's log window."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    # Define colors using RGB tuples (0-255, 255 for full opacity)
    color = (200, 200, 200, 255) # Light gray for INFO
    if level == "ERROR":
        color = (255, 80, 80, 255) # Lighter red for ERROR
    elif level == "WARNING":
        color = (255, 200, 0, 255) # Orange-yellow for WARNING
    elif level == "SUCCESS":
        color = (80, 255, 80, 255) # Brighter green for SUCCESS
    
    # Append message to the log window directly with color
    # Ensure log_window exists before attempting to add text to it
    if dpg.does_item_exist("log_window"):
        log_item = dpg.add_text(f"[{timestamp}] [{level}] {message}", parent="log_window", color=color)
        
        # Auto-scroll to bottom
        dpg.set_y_scroll("log_window", dpg.get_y_scroll_max("log_window"))
    else:
        print(f"Log Window Not Found: [{timestamp}] [{level}] {message}") # Fallback to print if GUI not ready

# --- Authentication Callback ---
def authenticate_callback():
    global logged_in_user, home_directory
    username = dpg.get_value("username_input")
    password = dpg.get_value("password_input")

    log_message(f"Attempting to authenticate user: {username}...", "INFO")
    
    # Call the headless authentication function
    auth_result, error_message = authenticate_user_headless(username, password, log_callback=log_message)

    if auth_result:
        logged_in_user = username
        home_directory = auth_result
        log_message(f"Authentication successful! Welcome, {logged_in_user}.", "SUCCESS")
        dpg.hide_item("auth_window")
        dpg.show_item("main_window")
        # FIX: Update main_window label here directly after successful login
        dpg.set_item_label("main_window", f"Backup Client - Logged in as: {logged_in_user}")
        # Load and display initial configurations or backups
        display_current_config()
        refresh_local_backups()
        refresh_server_backups()
        # Start the auto-backup scheduler if enabled
        start_auto_backup_scheduler()
    else:
        log_message(f"Authentication failed: {error_message}", "ERROR")

# --- Backup Operations ---
def run_full_backup():
    if not logged_in_user:
        log_message("Please log in first.", "WARNING")
        return
    log_message("Starting full system backup...", "INFO")
    threading.Thread(target=lambda: _run_full_backup_task(log_message), daemon=True).start()

def _run_full_backup_task(log_callback):
    success, message = full_system_backup(log_callback=log_callback)
    if success:
        log_message(f"Full backup complete: {message}", "SUCCESS")
        refresh_local_backups()
    else:
        log_message(f"Full backup failed: {message}", "ERROR")

def run_specific_backup():
    if not logged_in_user:
        log_message("Please log in first.", "WARNING")
        return
    specific_dir = dpg.get_value("specific_dir_input")
    if not specific_dir:
        log_message("Please enter a directory for specific backup.", "WARNING")
        return
    log_message(f"Starting specific directory backup for: {specific_dir}...", "INFO")
    threading.Thread(target=lambda: _run_specific_backup_task(specific_dir, log_message), daemon=True).start()

def _run_specific_backup_task(directory, log_callback):
    success, message = specific_directory_backup(directory, log_callback=log_callback)
    if success:
        log_message(f"Specific directory backup complete: {message}", "SUCCESS")
        refresh_local_backups()
    else:
        log_message(f"Specific directory backup failed: {message}", "ERROR")

def run_restore_backup():
    if not logged_in_user:
        log_message("Please log in first.", "WARNING")
        return
    selected_backup_files = dpg.get_value("local_backup_listbox")
    # FIX: Check if selected_backup_files is the default message or empty
    if not selected_backup_files or selected_backup_files == ["No local backups found"] or selected_backup_files == "No local backups found": 
        log_message("Please select a local backup to restore.", "WARNING")
        return
    
    # Ensure selected_backup_files is always a list for consistent handling
    if isinstance(selected_backup_files, str):
        selected_backup_files = [selected_backup_files]

    backup_filename = selected_backup_files[0] # Assume single selection for now
    
    restore_path = dpg.get_value("restore_path_input")
    if not restore_path:
        log_message("Please enter a destination path for restore.", "WARNING")
        return
    
    full_backup_path = os.path.join(Client.BACKUP_DIR, backup_filename) # Access BACKUP_DIR from Client
    
    log_message(f"Starting restore of {backup_filename} to {restore_path}...", "INFO")
    threading.Thread(target=lambda: _run_restore_backup_task(full_backup_path, restore_path, log_message), daemon=True).start()

def _run_restore_backup_task(backup_file, restore_path, log_callback):
    success, message = restore_backup(backup_file, restore_path, log_callback=log_callback)
    if success:
        log_message(f"Restore complete: {message}", "SUCCESS")
    else:
        log_message(f"Restore failed: {message}", "ERROR")

# --- Local Backup Management ---
def refresh_local_backups():
    log_message("Refreshing local backups...", "INFO")
    local_files = list_local_backups_headless(log_callback=log_message)
    if local_files:
        dpg.configure_item("local_backup_listbox", items=local_files, num_items=min(len(local_files), LISTBOX_VISIBLE_ITEMS)) # Adjust num_items
        log_message(f"Found {len(local_files)} local backup(s).", "INFO")
    else:
        dpg.configure_item("local_backup_listbox", items=["No local backups found"], num_items=1)
        log_message("No local backups found.", "INFO")

def delete_local_backup():
    if not logged_in_user:
        log_message("Please log in first.", "WARNING")
        return
    selected_backup_files = dpg.get_value("local_backup_listbox")
    # FIX: Check if selected_backup_files is the default message or empty
    if not selected_backup_files or selected_backup_files == "No local backups found" or selected_backup_files == ["No local backups found"]: 
        log_message("No local backup selected or available to delete.", "WARNING")
        return
    
    # Ensure selected_backup_files is always a list for consistent handling
    if isinstance(selected_backup_files, str):
        selected_backup_files = [selected_backup_files]

    backup_filename = selected_backup_files[0] # Assume single selection for now

    log_message(f"Attempting to delete local backup: {backup_filename}...", "INFO")
    success, message = delete_local_backup_headless(backup_filename, log_callback=log_message)
    if success:
        log_message(f"Local backup deleted: {message}", "SUCCESS")
        refresh_local_backups()
    else:
        log_message(f"Failed to delete local backup: {message}", "ERROR")

# --- Server Backup Management ---
def refresh_server_backups():
    if not logged_in_user:
        log_message("Please log in first.", "WARNING")
        return
    log_message("Refreshing server backups...", "INFO")
    server_files, error = list_server_backups_headless(home_directory, log_callback=log_message)
    if server_files:
        dpg.configure_item("server_backup_listbox", items=server_files, num_items=min(len(server_files), LISTBOX_VISIBLE_ITEMS))
        log_message(f"Found {len(server_files)} server backup(s).", "INFO")
    elif error:
        dpg.configure_item("server_backup_listbox", items=["Error listing server backups"], num_items=1)
        log_message(f"Error listing server backups: {error}", "ERROR")
    else:
        dpg.configure_item("server_backup_listbox", items=["No server backups found"], num_items=1)
        log_message("No server backups found.", "INFO")

def upload_selected_backup():
    if not logged_in_user:
        log_message("Please log in first.", "WARNING")
        return
    selected_backup_files = dpg.get_value("local_backup_listbox")
    if not selected_backup_files or selected_backup_files == "No local backups found" or selected_backup_files == ["No local backups found"]:
        log_message("No local backup selected or available to upload.", "WARNING")
        return
    
    if isinstance(selected_backup_files, str):
        selected_backup_files = [selected_backup_files]

    backup_filename = selected_backup_files[0]
    full_backup_path = os.path.join(Client.BACKUP_DIR, backup_filename) # Access BACKUP_DIR from Client

    log_message(f"Attempting to upload {backup_filename} to server...", "INFO")
    threading.Thread(target=lambda: _upload_task(full_backup_path, log_message), daemon=True).start()

def _upload_task(file_path, log_callback):
    success, message = upload_backup_headless(home_directory, file_path, log_callback=log_callback)
    if success:
        log_message(f"Upload complete: {message}", "SUCCESS")
        refresh_server_backups()
    else:
        log_message(f"Upload failed: {message}", "ERROR")

def download_selected_backup():
    if not logged_in_user:
        log_message("Please log in first.", "WARNING")
        return
    selected_server_files = dpg.get_value("server_backup_listbox")
    if not selected_server_files or selected_server_files == "No server backups found" or selected_server_files == ["No server backups found"]:
        log_message("No server backup selected or available to download.", "WARNING")
        return
    
    if isinstance(selected_server_files, str):
        selected_server_files = [selected_server_files]

    backup_filename = selected_server_files[0]
    
    # Download to local BACKUP_DIR
    download_destination = Client.BACKUP_DIR

    log_message(f"Attempting to download {backup_filename} from server...", "INFO")
    threading.Thread(target=lambda: _download_task(backup_filename, download_destination, log_message), daemon=True).start()

def _download_task(filename, destination, log_callback):
    success, message = download_backup_headless(home_directory, filename, destination, log_callback=log_callback)
    if success:
        log_message(f"Download complete: {message}", "SUCCESS")
        refresh_local_backups() # Update local list after download
    else:
        log_message(f"Download failed: {message}", "ERROR")

def delete_selected_server_backup():
    if not logged_in_user:
        log_message("Please log in first.", "WARNING")
        return
    selected_server_files = dpg.get_value("server_backup_listbox")
    if not selected_server_files or selected_server_files == "No server backups found" or selected_server_files == ["No server backups found"]:
        log_message("No server backup selected or available to delete.", "WARNING")
        return
    
    if isinstance(selected_server_files, str):
        selected_server_files = [selected_server_files]

    backup_filename = selected_server_files[0]

    log_message(f"Attempting to delete server backup: {backup_filename}...", "INFO")
    success, message = delete_server_backup_headless(home_directory, backup_filename, log_callback=log_message)
    if success:
        log_message(f"Server backup deleted: {message}", "SUCCESS")
        refresh_server_backups()
    else:
        log_message(f"Failed to delete server backup: {message}", "ERROR")

# --- Auto-Backup Configuration ---
def display_current_config():
    config = load_config(log_callback=log_message)
    dpg.set_value("auto_backup_enabled_checkbox", config.get("auto_backup_enabled", False))
    dpg.set_value("backup_type_radio", config.get("backup_type", "specific"))
    dpg.set_value("specific_dir_config_input", config.get("specific_dir", ""))
    dpg.set_value("frequency_radio", config.get("frequency", "daily"))
    dpg.set_value("time_input_config", config.get("time", "00:00"))
    log_message("Current backup configuration loaded.", "INFO")

def save_auto_backup_config():
    config = load_config(log_callback=log_message) # Load current config to avoid overwriting unrelated settings
    
    config["auto_backup_enabled"] = dpg.get_value("auto_backup_enabled_checkbox")
    config["backup_type"] = dpg.get_value("backup_type_radio")
    config["specific_dir"] = dpg.get_value("specific_dir_config_input")
    config["frequency"] = dpg.get_value("frequency_radio")
    config["time"] = dpg.get_value("time_input_config")

    success, message = save_config(config, log_callback=log_message)
    if success:
        log_message("Auto-backup configuration saved successfully.", "SUCCESS")
        start_auto_backup_scheduler() # Restart scheduler with new config
    else:
        log_message(f"Failed to save auto-backup configuration: {message}", "ERROR")

def start_auto_backup_scheduler():
    global auto_backup_scheduler_thread
    log_message("Attempting to start/restart auto-backup scheduler...", "INFO")
    
    # The auto_backup_scheduler function in Client.py handles stopping existing threads
    # and clearing jobs internally, so we just call it.
    # It also takes a log_callback
    auto_backup_scheduler(log_callback=log_message) 
    log_message("Auto-backup scheduler activated/restarted with current configuration (if enabled).", "INFO")


# --- GUI Setup ---
dpg.create_context()
dpg.create_viewport(title='Backup System Client', width=1000, height=750, resizable=True) # Increased size
dpg.setup_dearpygui()

# --- Global Font ---
with dpg.font_registry():
    # Use a common font available on Kali Linux (DejaVuSans is usually safe)
    # Check /usr/share/fonts/truetype/ for available fonts on your Kali system
    # If this path doesn't work, try:
    # default_font = dpg.add_font("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 16)
    # Or simply use DPG's default font if you don't care about a specific one:
    default_font = dpg.add_font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    dpg.bind_font(default_font)


# --- Theme Setup (for a cleaner look) ---
with dpg.theme(tag="global_theme"):
    with dpg.theme_component(dpg.mvAll):
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 5, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 5, category=dpg.mvThemeCat_Core)
        dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 8, category=dpg.mvThemeCat_Core) # Increased padding
        dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 4, category=dpg.mvThemeCat_Core) # Spacing between items

        # Colors for a slightly darker, modern look
        dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (25, 25, 25, 255), category=dpg.mvThemeCat_Core) # Dark background
        dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (50, 70, 90, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_Button, (60, 60, 60, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 80, 80, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (100, 100, 100, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 40, 255), category=dpg.mvThemeCat_Core) # Input/ListBox background
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (50, 50, 50, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (60, 60, 60, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_Tab, (40, 40, 40, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_TabActive, (50, 70, 90, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (60, 80, 100, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_Text, (220, 220, 220, 255), category=dpg.mvThemeCat_Core) # Light gray text
        dpg.add_theme_color(dpg.mvThemeCol_Header, (50, 70, 90, 255), category=dpg.mvThemeCat_Core) # For selectable items in listbox
        dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (60, 80, 100, 255), category=dpg.mvThemeCat_Core)
        dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (70, 90, 110, 255), category=dpg.mvThemeCat_Core)

dpg.bind_theme("global_theme")


# --- Authentication Window ---
with dpg.window(tag="auth_window", label="Login - Backup System", no_close=True, no_resize=True, no_move=True):
    # Centering content
    dpg.add_spacer(height=50) # Top margin
    with dpg.group(horizontal=True):
        # Calculate approximate left spacer to center login group given a fixed group width
        # (Viewport width - Group width) / 2
        login_group_width = ITEM_WIDTH # Use ITEM_WIDTH as the width of the login elements
        try:
            viewport_width = dpg.get_viewport_width()
            left_spacer_width = (viewport_width / 2) - (login_group_width / 2)
            if left_spacer_width < 0: # Ensure it's not negative
                left_spacer_width = 0
            dpg.add_spacer(width=left_spacer_width) 
        except Exception:
            # Fallback if viewport size isn't available yet
            dpg.add_spacer(width=200) # Default left margin

        with dpg.group(): # Group for login elements
            dpg.add_text("Welcome to the Secure Backup System", color=(100, 180, 255, 255))
            dpg.add_separator()
            dpg.add_spacer(height=10)

            dpg.add_input_text(label="Username", tag="username_input", default_value="user", width=ITEM_WIDTH)
            dpg.add_input_text(label="Password", tag="password_input", password=True, default_value="password", width=ITEM_WIDTH)
            dpg.add_spacer(height=10)
            dpg.add_button(label="Login", callback=authenticate_callback, width=ITEM_WIDTH, height=BUTTON_HEIGHT)
    dpg.add_spacer(height=50) # Bottom margin

# --- Main Application Window ---
with dpg.window(tag="main_window", label="Backup Client - Logged in as: ", show=False, width=1000, height=750):
    # The main window's label is updated directly in authenticate_callback after login

    with dpg.tab_bar(tag="main_tab_bar"):
        # --- Backup/Restore Tab ---
        with dpg.tab(label="Backup & Restore", tag="backup_restore_tab"):
            dpg.add_spacer(height=GROUP_SPACING)
            with dpg.group(horizontal=True, width=-1): # Use width=-1 to make the group expand
                # Left Column: Backup Operations
                with dpg.child_window(tag="backup_ops_panel", width=-1, height=dpg.get_viewport_height() - 150):
                    dpg.add_text("Initiate Backup Operations:", color=(150, 200, 255, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    dpg.add_button(label="Perform Full System Backup", callback=run_full_backup, width=-1, height=BUTTON_HEIGHT*1.5) # -1 for full width
                    dpg.add_spacer(height=GROUP_SPACING)
                    
                    dpg.add_text("Specific Directory Backup:", color=(150, 200, 255, 255))
                    dpg.add_input_text(label="Source Path", tag="specific_dir_input", hint="e.g., /home/user/documents", width=ITEM_WIDTH)
                    dpg.add_button(label="Backup Specific Directory", callback=run_specific_backup, width=-1, height=BUTTON_HEIGHT)
                    dpg.add_spacer(height=GROUP_SPACING)

                dpg.add_spacer(width=GROUP_SPACING) # Space between columns

                # Right Column: Local Backups & Restore
                with dpg.child_window(tag="local_restore_panel", width=-1, height=dpg.get_viewport_height() - 150):
                    dpg.add_text("Local Backups & Restore:", color=(150, 200, 255, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    # FIX: Removed 'height' keyword; using num_items for listbox height
                    dpg.add_listbox(label="Select Local Backup", tag="local_backup_listbox", num_items=LISTBOX_VISIBLE_ITEMS, width=-1)
                    
                    with dpg.group(horizontal=True):
                        # FIX: Removed 'weight=0.5' - width=-1 will distribute equally
                        dpg.add_button(label="Refresh Local", callback=refresh_local_backups, width=-1, height=BUTTON_HEIGHT)
                        dpg.add_button(label="Delete Local", callback=delete_local_backup, width=-1, height=BUTTON_HEIGHT)
                    dpg.add_spacer(height=GROUP_SPACING)

                    dpg.add_text("Restore Selected Backup:", color=(150, 200, 255, 255))
                    dpg.add_input_text(label="Destination Path", tag="restore_path_input", hint="e.g., /tmp/restore", width=ITEM_WIDTH)
                    dpg.add_button(label="Restore Selected Backup", callback=run_restore_backup, width=-1, height=BUTTON_HEIGHT)
                    dpg.add_spacer(height=GROUP_SPACING)

        # --- Server Interaction Tab ---
        with dpg.tab(label="Server Interaction", tag="server_tab"):
            dpg.add_spacer(height=GROUP_SPACING)
            with dpg.group(horizontal=True, width=-1): # Use width=-1 to make the group expand
                # Left Column: Server Backups
                with dpg.child_window(tag="server_list_panel", width=-1, height=dpg.get_viewport_height() - 150):
                    dpg.add_text("Server Backups Overview:", color=(150, 200, 255, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    # FIX: Removed 'height' keyword; using num_items for listbox height
                    dpg.add_listbox(label="Select Server Backup", tag="server_backup_listbox", num_items=LISTBOX_VISIBLE_ITEMS, width=-1)
                    dpg.add_button(label="Refresh Server Backups", callback=refresh_server_backups, width=-1, height=BUTTON_HEIGHT)
                    dpg.add_spacer(height=GROUP_SPACING)

                dpg.add_spacer(width=GROUP_SPACING) # Space between columns

                # Right Column: Upload/Download/Delete Server
                with dpg.child_window(tag="server_actions_panel", width=-1, height=dpg.get_viewport_height() - 150):
                    dpg.add_text("Server Actions:", color=(150, 200, 255, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    dpg.add_button(label="Upload Selected Local Backup", callback=upload_selected_backup, width=-1, height=BUTTON_HEIGHT)
                    dpg.add_spacer(height=GROUP_SPACING/2)
                    dpg.add_button(label="Download Selected Server Backup", callback=download_selected_backup, width=-1, height=BUTTON_HEIGHT)
                    dpg.add_spacer(height=GROUP_SPACING/2)
                    # FIX: Removed 'weight=0.5' - this button is alone in its group, so weight is not applicable here.
                    dpg.add_button(label="Delete Selected Server Backup", callback=delete_selected_server_backup, width=-1, height=BUTTON_HEIGHT)
                    dpg.add_spacer(height=GROUP_SPACING)

        # --- Auto-Backup Config Tab ---
        with dpg.tab(label="Auto-Backup Config", tag="auto_backup_tab"):
            dpg.add_spacer(height=GROUP_SPACING)
            with dpg.group(horizontal=True, width=-1): # Use width=-1 to make the group expand
                # Center content for Auto-Backup
                # Calculate approximate left spacer to center config group
                config_group_width = ITEM_WIDTH * 1.5
                try:
                    viewport_width = dpg.get_viewport_width()
                    left_spacer_config_width = (viewport_width / 2) - (config_group_width / 2)
                    if left_spacer_config_width < 0:
                        left_spacer_config_width = 0
                    dpg.add_spacer(width=left_spacer_config_width)
                except Exception:
                    dpg.add_spacer(width=100) # Default left margin
                
                with dpg.group(width=config_group_width): # A bit wider for config
                    dpg.add_text("Configure Automated Backups:", color=(150, 200, 255, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    dpg.add_checkbox(label="Enable Auto-Backup", tag="auto_backup_enabled_checkbox", default_value=False)
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    dpg.add_text("Backup Type:", color=(200, 200, 200, 255))
                    dpg.add_radio_button(["full", "specific"], label="##BackupTypeRadio", tag="backup_type_radio", default_value="specific", horizontal=True)
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    dpg.add_input_text(label="Specific Directory", tag="specific_dir_config_input", hint="e.g., /home/user/docs", width=ITEM_WIDTH*1.5)
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    dpg.add_text("Frequency:", color=(200, 200, 200, 255))
                    dpg.add_radio_button(["daily", "weekly", "monthly"], label="##FrequencyRadio", tag="frequency_radio", default_value="daily", horizontal=True)
                    dpg.add_spacer(height=GROUP_SPACING/2)

                    dpg.add_input_text(label="Time (HH:MM 24-hour)", tag="time_input_config", default_value="00:00", hint="e.g., 03:30", width=ITEM_WIDTH)
                    dpg.add_spacer(height=GROUP_SPACING)

                    dpg.add_button(label="Save Configuration", callback=save_auto_backup_config, width=-1, height=BUTTON_HEIGHT)
                    dpg.add_spacer(height=GROUP_SPACING/2)
                    dpg.add_button(label="Reload Config", callback=display_current_config, width=-1, height=BUTTON_HEIGHT)

                # dpg.add_spacer(width=100) # No need for a right spacer if centering with left spacer and group width

        # --- Log Tab ---
        with dpg.tab(label="Application Log", tag="log_tab"):
            # dpg.add_spacer(height=GROUP_SPACING) # Add some top padding
            dpg.add_child_window(tag="log_window", autosize_x=True, autosize_y=True, border=True) # Added border for visibility

# Set initial window position and size
dpg.set_primary_window("auth_window", True)
dpg.set_viewport_pos([50, 50]) # Slightly offset from top-left
dpg.set_viewport_width(1000)
dpg.set_viewport_height(750)

dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()