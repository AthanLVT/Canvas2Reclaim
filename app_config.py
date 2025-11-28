import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import re
import subprocess
import threading
import sys 
import shutil 

# --- Configuration File Paths (Must match the worker script's expectations) ---
CONFIG_FILE = 'config.py'
NEW_ASSIGNMENTS_FILE = 'new_assignment_names.json'
# File 1: Stored Assignment List
SEEN_ASSIGNMENTS_FILE = 'seen_assignments.json' 
# NEW: Backup of Stored Assignment List
PREV_SEEN_ASSIGNMENTS_FILE = 'prev_seen_assignments.json' 
# File 2: Time allocation/Status Data
TIMED_ASSIGNMENTS_FILE = 'timed_assignments.json' 
# File 3: Time allocation Rules
TIME_ALLOCATION_RULES_FILE = 'assignment_time_rules.json'

# --- Python Scripts in the Workflow ---
SCRAPER_SCRIPT = 'canvas_scrape_assignments.py'
ALLOCATOR_SCRIPT = 'time_allocator.py'
RECLAIM_SCRIPT = 'reclaim_task_creator.py'


class SyncConfigApp(tk.Tk):
    """
    A simple Tkinter application to manage configuration and data files
    and execute the synchronization workflow.
    """
    def __init__(self):
        super().__init__()
        self.title("Canvas & Reclaim.ai Local Config Manager")
        self.geometry("900x750")
        self.configure(bg='#f0f0f0')

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        # Event for pausing the worker thread during the Selenium warning popup
        self.continue_event = threading.Event()
        self.pipeline_cancelled = False

        # Initialize data structures
        self.settings = {}
        self.data = {
            NEW_ASSIGNMENTS_FILE: '[]',
            TIMED_ASSIGNMENTS_FILE: '[]',
            SEEN_ASSIGNMENTS_FILE: '[]',
            PREV_SEEN_ASSIGNMENTS_FILE: '[]', 
            TIME_ALLOCATION_RULES_FILE: '{}' 
        }
        self.load_all_files()

        # Create tabs - Tab 3 removed from the main notebook
        self.create_run_tab()     # <-- 1st: Main Tab
        self.create_settings_tab() # <-- 2nd: Settings Tab
        
        # Initialize Style
        self.style = ttk.Style()
        self.style.configure('Accent.TButton', font=('Arial', 12, 'bold'), foreground='black', background='#4CAF50')
        self.style.map('Accent.TButton', background=[('active', '#66BB6A')])
        self.style.configure('Danger.TButton', font=('Arial', 10, 'bold'), foreground='red', background='#CC0000') 
        self.style.map('Danger.TButton', background=[('active', '#FF3333')])


    # --- New Navigation Function ---
    def go_to_settings_and_open_guide(self):
        """Switches to the Settings tab and opens the Setup Guide window."""
        # Switch to the Settings tab (index 1, since Main is 0)
        self.notebook.select(1)
        # Open the setup guide
        self.create_setup_guide_widget()
        
    # --- File Loading and Saving (Updated for CANVAS_URL) ---

    def load_config_py(self):
        """Loads configuration variables from config.py."""
        if not os.path.exists(CONFIG_FILE):
            print(f"INFO: {CONFIG_FILE} not found. Starting with default settings.")
            return

        with open(CONFIG_FILE, 'r') as f:
            content = f.read()

        mapping = {
            # Added CANVAS_URL field
            'CANVAS_URL': r'CANVAS_URL\s*=\s*(?:r?["\'](.+?)["\'])',
            # Keeping CANVAS_ACCESS_TOKEN for the UI element, reading CANVAS_TOKEN or CANVAS_ACCESS_TOKEN
            'CANVAS_ACCESS_TOKEN': r'(?:CANVAS_ACCESS_TOKEN|CANVAS_TOKEN)\s*=\s*(?:r?["\'](.+?)["\'])', 
            'RECLAIM_EMAIL': r'RECLAIM_EMAIL\s*=\s*(?:r?["\'](.+?)["\'])',
            'RECLAIM_PASSWORD': r'RECLAIM_PASSWORD\s*=\s*(?:r?["\'](.+?)["\'])',
            'CHROME_PROFILE_PATH': r'CHROME_PROFILE_PATH\s*=\s*r?["\'](.+?)["\']',
            'CHROME_PROFILE_NAME': r'CHROME_PROFILE_NAME\s*=\s*(?:r?["\'](.+?)["\'])',
        }

        for key, pattern in mapping.items():
            match = re.search(pattern, content, re.DOTALL)
            if match:
                self.settings[key] = match.group(1).strip()
            else:
                self.settings[key] = ''

    def load_json_data(self, filename):
        """Loads JSON data from local files."""
        # Determine the expected default content
        is_rules_file = filename == TIME_ALLOCATION_RULES_FILE
        default_content = '{}' if is_rules_file else '[]'
        
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                    json.loads(content) 
                    self.data[filename] = content
            except json.JSONDecodeError:
                messagebox.showerror("JSON Error", f"File '{filename}' contains invalid JSON. Resetting to default.")
                self.data[filename] = default_content
            except Exception as e:
                print(f"Error loading {filename}: {e}")
        else:
            self.data[filename] = default_content
            print(f"INFO: {filename} not found. Created empty data.")

    def load_all_files(self):
        """Initializes settings and data by loading all local files."""
        self.load_config_py()
        self.load_json_data(SEEN_ASSIGNMENTS_FILE)
        self.load_json_data(PREV_SEEN_ASSIGNMENTS_FILE) # Load the new backup file
        self.load_json_data(NEW_ASSIGNMENTS_FILE)
        self.load_json_data(TIMED_ASSIGNMENTS_FILE)
        self.load_json_data(TIME_ALLOCATION_RULES_FILE) 

    def save_settings(self):
        """Writes configuration variables to config.py."""
        try:
            # Retrieve the new Canvas URL
            canvas_url = self.canvas_url_entry.get() 
            token = self.token_entry.get()
            email = self.email_entry.get()
            password = self.password_entry.get()
            path = self.path_entry.get()
            profile = self.profile_entry.get()

            content = f"""# Local Configuration for Reclaim Sync Script
# WARNING: Do not share this file. It contains sensitive credentials.

CANVAS_URL = "{canvas_url}"
CANVAS_ACCESS_TOKEN = "{token}"
RECLAIM_EMAIL = "{email}"
RECLAIM_PASSWORD = "{password}"
CHROME_PROFILE_PATH = r"{path.replace('\\', '/')}" # Uses raw string for Windows path safety
CHROME_PROFILE_NAME = "{profile}"
"""
            with open(CONFIG_FILE, 'w') as f:
                f.write(content)

            messagebox.showinfo("Success", f"Settings successfully saved to {CONFIG_FILE}.")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save settings: {e}")

    def save_json_data(self, filename, text_widget):
        """Writes the content of the text area to a JSON file, after validation."""
        content = text_widget.get("1.0", tk.END).strip()
        
        try:
            json.loads(content)
        except json.JSONDecodeError:
            messagebox.showerror("Validation Error", f"Content in {filename} is not valid JSON. Please correct it.")
            return

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("Success", f"Data successfully saved to {filename}.")
            self.data[filename] = content 
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save data to {filename}: {e}")

    # --- Utility Reset Function (Unchanged) ---
    def reset_json_file(self, filenames):
        """Resets one or more JSON files to '[]' or '{}' and updates the data model and Data tab if open."""
        
        if not isinstance(filenames, list):
            filenames = [filenames]
        
        file_list_str = ', '.join([f"'{f}'" for f in filenames])
        
        if not messagebox.askyesno("Confirm Reset", 
                                   f"Are you sure you want to reset the following files?\n{file_list_str}\nThis action cannot be undone and will delete all stored entries/rules."):
            return
        
        success_count = 0
        
        for filename in filenames:
            try:
                # Logic Fix: Rules file must be initialized as an object {}
                if filename == TIME_ALLOCATION_RULES_FILE:
                    content_to_write = '{}'
                else:
                    content_to_write = '[]'
                    
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content_to_write)
                
                self.data[filename] = content_to_write # Update internal data model

                # Logic to update the correct text widget if the Data window is open
                if hasattr(self, 'seen_assignments_text') and self.seen_assignments_text.winfo_exists():
                    if filename == SEEN_ASSIGNMENTS_FILE:
                        self.seen_assignments_text.delete('1.0', tk.END)
                        self.seen_assignments_text.insert(tk.END, content_to_write)
                    elif filename == TIMED_ASSIGNMENTS_FILE:
                        self.timed_assignments_text.delete('1.0', tk.END)
                        self.timed_assignments_text.insert(tk.END, content_to_write)
                    elif filename == TIME_ALLOCATION_RULES_FILE:
                        self.rules_assignments_text.delete('1.0', tk.END)
                        self.rules_assignments_text.insert(tk.END, content_to_write)
                
                success_count += 1
            except Exception as e:
                messagebox.showerror("Reset Error", f"Failed to reset '{filename}': {e}")
        
        if success_count == len(filenames):
             messagebox.showinfo("Success", f"All specified files ({file_list_str}) have been successfully reset.")
             
    # --- Restore Function (Unchanged) ---
    def restore_previous_sync(self):
        """
        Replaces seen_assignments.json content with the backup from prev_seen_assignments.json.
        """
        backup_content = self.data.get(PREV_SEEN_ASSIGNMENTS_FILE, '[]') # Default to empty list string if somehow missing
        
        if not os.path.exists(PREV_SEEN_ASSIGNMENTS_FILE):
            messagebox.showinfo("Restore Failed", "The backup file (prev_seen_assignments.json) does not exist to restore from.")
            return

        # Proceed with copy.
        try:
            # 1. Write the backup content to the main file
            with open(SEEN_ASSIGNMENTS_FILE, 'w', encoding='utf-8') as f:
                f.write(backup_content)
            
            # 2. Update the internal data model
            self.data[SEEN_ASSIGNMENTS_FILE] = backup_content
            
            # 3. Update the Data Window UI if visible
            if hasattr(self, 'seen_assignments_text') and self.seen_assignments_text.winfo_exists():
                self.seen_assignments_text.delete('1.0', tk.END)
                self.seen_assignments_text.insert(tk.END, backup_content)
                
            messagebox.showinfo("Restore Complete", "Successfully restored seen_assignments.json from the previous sync.")
            self.append_to_console("--- RESTORE COMPLETE: seen_assignments.json has been reverted to the last successful state. ---")
            
        except Exception as e:
            messagebox.showerror("Restore Error", f"Failed to restore previous sync data: {e}")

    # --- UI Creation: Settings Tab (Updated for CANVAS_URL) ---
    def create_settings_tab(self):
        """Creates the tab for entering and saving user credentials and paths."""
        settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(settings_frame, text="2. Settings (config.py)")

        def create_input_row(parent, label_text, var_key, is_password=False, placeholder=""):
            row_frame = ttk.Frame(parent)
            row_frame.pack(fill='x', pady=5)
            label = ttk.Label(row_frame, text=label_text, width=35)
            label.pack(side='left', padx=5, anchor='w')
            entry_var = tk.StringVar(value=self.settings.get(var_key, placeholder))
            entry = ttk.Entry(row_frame, textvariable=entry_var, width=50, show='*' if is_password else '')
            entry.pack(side='left', expand=True, fill='x', padx=5)
            return entry
        
        # --- SETUP BUTTON AND HEADER FRAME ---
        header_frame = ttk.Frame(settings_frame)
        header_frame.pack(fill='x', pady=10)

        ttk.Label(header_frame, text="Enter your access details below. This will create or update 'config.py'.", 
                      foreground='blue').pack(side='left', padx=5, anchor='w')
        
        setup_button = ttk.Button(header_frame, text="Setup Guide ⚙️", command=self.create_setup_guide_widget)
        setup_button.pack(side='right', padx=5)
        
        # NEW FIELD: CANVAS URL
        self.canvas_url_entry = create_input_row(settings_frame, "Canvas Base URL (Required):", 'CANVAS_URL', placeholder="https://canvas.vt.edu")
        
        # Existing Fields
        self.token_entry = create_input_row(settings_frame, "Canvas Access Token (Required):", 'CANVAS_ACCESS_TOKEN', is_password=True, placeholder="sk_...")
        self.email_entry = create_input_row(settings_frame, "Reclaim.ai Email (Required):", 'RECLAIM_EMAIL', placeholder="user@example.com")
        self.password_entry = create_input_row(settings_frame, "Reclaim.ai Password (Required):", 'RECLAIM_PASSWORD', is_password=True, placeholder="••••••••")
        
        ttk.Separator(settings_frame, orient='horizontal').pack(fill='x', pady=10)

        self.path_entry = create_input_row(settings_frame, "Chrome Profile Path (Required for Selenium):", 'CHROME_PROFILE_PATH', placeholder="C:\\Users\\YourName\\AppData\\Local\\Google\\Chrome\\User Data")
        self.profile_entry = create_input_row(settings_frame, "Chrome Profile Name (e.g., Default):", 'CHROME_PROFILE_NAME', placeholder="Default")

        save_button = ttk.Button(settings_frame, text="Save Settings to config.py", command=self.save_settings)
        save_button.pack(pady=20)
        
        # --- DATA VIEW BUTTON (NEW LOCATION FOR TAB 3 CONTENT) ---
        data_view_button = ttk.Button(settings_frame, text="Display / Edit .json Files 🗃️", 
                              command=self.open_data_files_window)
        data_view_button.pack(pady=20)

        # --- RESET BUTTONS FRAME ---
        reset_frame = ttk.LabelFrame(settings_frame, text="Data Reset Options (Use with Caution)", padding="10")
        reset_frame.pack(fill='x', pady=10)

        ttk.Label(reset_frame, text="Resetting these lists will erase historical data, allocation statuses, and all rules.", foreground='red').pack(pady=5)

        # Frame for the two horizontal buttons
        reset_buttons_frame = ttk.Frame(reset_frame)
        reset_buttons_frame.pack(fill='x', pady=5)
        
        # 1. Stored Assignments Reset Button
        reset_seen_button = ttk.Button(reset_buttons_frame, text="Reset Stored Assignments (seen_assignments.json) 🗑️",
                                        command=lambda: self.reset_json_file(SEEN_ASSIGNMENTS_FILE))
        reset_seen_button.pack(side='left', padx=5, fill='x', expand=True)

        # 2. Combined Time Allocation Reset Button 
        time_files_to_reset = [TIMED_ASSIGNMENTS_FILE, TIME_ALLOCATION_RULES_FILE]
        reset_time_data_button = ttk.Button(reset_buttons_frame, text="Reset Time Allocation DATA & RULES 🗑️",
                                        style='Danger.TButton',
                                        command=lambda: self.reset_json_file(time_files_to_reset))
        reset_time_data_button.pack(side='right', padx=5, expand=True)
        
    # --- Setup Guide Widget (Unchanged) ---
    def create_setup_guide_widget(self):
        """Creates a Toplevel widget to display setup instructions."""
        guide_window = tk.Toplevel(self)
        guide_window.title("Configuration Setup Guide")
        guide_window.geometry("600x450")
        guide_window.grab_set() 

        text_content = """
## 💡 Canvas & Reclaim.ai Setup Instructions

1.  **Canvas Access Token (Required)**
    * **Find it:** Canvas -> Account -> Settings -> Approved Integrations -> [+ New Access Token]
    * **Configure:** Purpose= "Canvas2Reclaim", date= furthest possible date
    * **Action:** [Generate Token] -> **Copy Token** to the **Canvas Access Token Field** in the settings tab.

2.  **Reclaim.ai Email & Password (Required)**
    * **Reclaim.ai Email:** Likely your Google email (used to sign into Reclaim.ai).
    * **Reclaim.ai Password:** Likely your Google password (used by the script for login).

3.  **Chrome Profile Path (Required for Selenium)**
    * **Find it:** Press **[Windows Key + R]** (Run dialog).
    * **Paste:** `C:\\Users\\%USERNAME%\\AppData\\Local\\Google\\Chrome\\User Data` (Without quotes).
    * **Action:** [OK] -> **Copy the resulting folder path** (in the form `C:\\Users\\[user]\\AppData\\Local\\Google\\Chrome\\User Data`) -> **Paste** in the **Chrome Profile Path Field**.

4.  **Chrome Profile Name (Required for Selenium)**
    * **Find it:** Look inside the folder path found in step 3.
    * **Identify:** The profile name is the **folder name** inside `User Data` that holds your session, most commonly **"Default"** or **"Profile 1"**.
    * **Action:** **Paste the exact folder name** in the **Chrome Profile Name Field**
"""
        guide_text = scrolledtext.ScrolledText(guide_window, wrap=tk.WORD, font=("Arial", 10), 
                                                bg='#f9f9f9', bd=0, padx=10, pady=10)
        guide_text.insert(tk.END, text_content)
        guide_text.config(state=tk.DISABLED)
        guide_text.pack(expand=True, fill='both')

        close_button = ttk.Button(guide_window, text="Understood & Close", command=guide_window.destroy)
        close_button.pack(pady=10)

    # --- Time Estimation Prompt Widget (Unchanged) ---
    def prompt_for_time_estimate(self, assignment_name):
        """Creates a Toplevel widget to ask the user for a time estimate."""
        
        self.user_time_input = None 
        
        prompt_window = tk.Toplevel(self)
        prompt_window.title("Time Estimate Required")
        prompt_window.geometry("450x180")
        prompt_window.transient(self) 
        prompt_window.grab_set() 
        prompt_window.lift()

        # Instruction Label
        ttk.Label(prompt_window, text=f"Enter time required for: {assignment_name}", 
                  font=('Arial', 10, 'bold')).pack(pady=10, padx=10)
        
        # Example Label
        ttk.Label(prompt_window, text="Time in hours (e.g., 1.5 hours = 1hr 30min).", foreground='blue').pack(padx=10)
        
        # Input Field
        input_var = tk.StringVar(value="1.0")
        input_entry = ttk.Entry(prompt_window, textvariable=input_var, width=15)
        input_entry.pack(pady=5, padx=10)
        input_entry.focus_set()

        def submit_time():
            try:
                # Basic validation
                time_val = float(input_var.get())
                if time_val <= 0:
                     raise ValueError("Time must be greater than zero.")
                self.user_time_input = time_val
                prompt_window.destroy()
            except ValueError:
                messagebox.showerror("Invalid Input", "Please enter a valid positive number (e.g., 1.5).")
        
        # Submit Button
        submit_button = ttk.Button(prompt_window, text="Submit Time", command=submit_time)
        submit_button.pack(pady=10)
        
        # Bind <Return> key to submit
        input_entry.bind('<Return>', lambda event: submit_time())

        # Wait for the user to close the window
        self.wait_window(prompt_window)
        
        return self.user_time_input

    # --- JSON Data Management Window (Unchanged) ---

    def create_json_editor(self, parent, title, filename):
        """Helper function to create a JSON editor frame."""
        editor_frame = ttk.LabelFrame(parent, text=title, padding="10")
        editor_frame.pack(fill='both', expand=True, pady=10)

        text_area = scrolledtext.ScrolledText(editor_frame, wrap=tk.WORD, height=15, font=("Consolas", 10), 
                                                 bg='#ffffff', bd=1, relief="solid")
        
        # Load content from self.data
        text_area.insert(tk.END, self.data.get(filename, '[]')) 
        text_area.pack(fill='both', expand=True)

        # Only allow saving the main files (not the backup file)
        if filename != PREV_SEEN_ASSIGNMENTS_FILE:
            save_button = ttk.Button(editor_frame, text=f"Save {filename}", 
                                                     command=lambda: self.save_json_data(filename, text_area))
            save_button.pack(pady=5)
        
        return text_area


    def populate_data_files_ui(self, parent_frame):
        """Populates the UI elements for editing JSON data files within a given parent frame."""
        # 1. seen_assignments.json 
        self.seen_assignments_text = self.create_json_editor(
            parent_frame, 
            "seen_assignments.json (Assignment Tracker - Current)", 
            SEEN_ASSIGNMENTS_FILE
        )
        
        # 2. Backup File (No Save Button)
        self.create_json_editor(
            parent_frame, 
            "prev_seen_assignments.json (Assignment Tracker - Backup)", 
            PREV_SEEN_ASSIGNMENTS_FILE
        )

        # 3. timed_assignments.json
        self.timed_assignments_text = self.create_json_editor(
            parent_frame, 
            "timed_assignments.json (Time Allocated/Synced Status)", 
            TIMED_ASSIGNMENTS_FILE
        )
        # 4. assignment_time_rules.json 
        self.rules_assignments_text = self.create_json_editor(
            parent_frame, 
            "assignment_time_rules.json (Time Allocation Rules)", 
            TIME_ALLOCATION_RULES_FILE
        )

    def open_data_files_window(self):
        """Creates a Toplevel window to display and edit all JSON data files."""
        data_window = tk.Toplevel(self)
        data_window.title("Configuration Data Files (*.json)")
        data_window.geometry("800x800")
        data_window.grab_set() 
        data_window.transient(self)

        # Frame to hold all editors
        data_frame = ttk.Frame(data_window, padding="10")
        data_frame.pack(expand=True, fill='both')

        # Populate the content of the old Tab 3
        self.populate_data_files_ui(data_frame)
        
        close_button = ttk.Button(data_window, text="Close Window", command=data_window.destroy)
        close_button.pack(pady=10)

    # --- New Warning Pop-up (UPDATED) ---
    def display_selenium_warning(self):
        """Displays the crucial warning before starting Selenium and waits for user acknowledgment."""
        self.continue_event.clear() # Clear the event before showing the window
        self.pipeline_cancelled = False
        
        warning_window = tk.Toplevel(self)
        warning_window.title("CRITICAL STEP: Hands-Off Automation")
        warning_window.geometry("600x400")
        warning_window.transient(self) 
        warning_window.grab_set() 
        warning_window.lift()

        # Big Warning Text
        ttk.Label(warning_window, text="Do not touch keyboard or mouse until sync is complete.", 
                  font=('Arial', 16, 'bold'), foreground='darkred', wraplength=550, justify=tk.CENTER).pack(pady=(20, 10), padx=10)

        # "Unless" Text
        ttk.Label(warning_window, text="Unless:", 
                  font=('Arial', 12, 'italic')).pack(pady=(10, 5), padx=10, anchor='w')

        # Warning from Main Tab (SAME FONT SIZE as Unless)
        # Note: The original warning text was slightly different from the text requested here, using the requested text.
        manual_warning_text = "if chrome opens but nothing happens, close out of each individual tab until chrome closes, then click the restore button on the home page, then sync again"
        ttk.Label(warning_window, text=manual_warning_text, font=('Arial', 12, 'italic'), 
                  foreground='darkred', wraplength=550, justify=tk.LEFT).pack(pady=5, padx=20, anchor='w')

        # Positive Note (SHORTENED)
        positive_note = "if reclaim opens up on its own, its working correctly."
        ttk.Label(warning_window, text=positive_note, font=('Arial', 12, 'italic'), 
                  foreground='green', wraplength=550, justify=tk.LEFT).pack(pady=5, padx=20, anchor='w')
        
        # Reminder Text
        ttk.Label(warning_window, text="(These can be found on the main page)", 
                  font=('Arial', 10, 'italic'), foreground='gray').pack(pady=(5, 10), padx=10)
        
        # Prompt and Button
        ttk.Label(warning_window, text="Press when ready:", 
                  font=('Arial', 11)).pack(pady=(10, 5))
        
        def acknowledge():
            self.continue_event.set() # Set the event to release the worker thread
            warning_window.destroy()

        def on_closing():
            # If the user closes the window manually, treat it as cancellation
            self.pipeline_cancelled = True
            messagebox.showinfo("Sync Interrupted", "Automation phase cancelled by user.")
            self.continue_event.set() # Release the lock so the thread can terminate gracefully
            warning_window.destroy()

        continue_button = ttk.Button(warning_window, text="Ok I understand, continue", command=acknowledge, style='Accent.TButton')
        continue_button.pack(pady=15, ipadx=10, ipady=5)
        
        warning_window.protocol("WM_DELETE_WINDOW", on_closing)

    # --- UI Creation: Run Sync Tab (Main) (Unchanged) ---

    def create_run_tab(self):
        """Creates the tab for running the full synchronization workflow."""
        run_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(run_frame, text="1. Main")

        # Header frame for Note, Setup Button, and Restore Button
        header_frame = ttk.Frame(run_frame)
        header_frame.pack(fill='x', pady=10)

        # NEW: Navigate to Setup Button (Left)
        setup_nav_button = ttk.Button(header_frame, text="⚙️ Navigate to Setup", 
                                      command=self.go_to_settings_and_open_guide)
        setup_nav_button.pack(side='left', padx=10, anchor='w')
        
        # Restore Button (Right)
        restore_button = ttk.Button(header_frame, text="↩️ Restore Previous Sync", 
                                    style='Danger.TButton', 
                                    command=self.restore_previous_sync)
        restore_button.pack(side='right', padx=10)

        # Note/Instruction (AMENDED TEXT)
        instruction_text = (
            "☑️ POSITIVE NOTE: If reclaim opens up on its own, its working correctly and you may need to wait for it to start adding tasks so don't close Chrome.\n\n"
            "⚠️ WARNING: If sync button opens chrome but nothing happens, Close out of each individual chrome tab until chrome closes, then press the restore button, then sync again"
        )
        ttk.Label(run_frame, text=instruction_text, foreground='blue', wraplength=800, justify=tk.LEFT).pack(fill='x', padx=10, anchor='w')
        
        # CRITICAL WARNING LABEL
        warning_text = "🚨 IMPORTANT: CLOSE ALL CHROME WINDOWS AND TABS BEFORE RUNNING SYNC 🚨"
        ttk.Label(run_frame, text=warning_text, font=('Arial', 12, 'bold'), foreground='darkred', background='#ffdddd', relief='solid', borderwidth=1, padding=5).pack(pady=10)
        
        # Run Button
        self.run_button = ttk.Button(run_frame, text="▶ START FULL SYNC WORKFLOW", 
                                                 command=self.start_sync_thread, 
                                                 style='Accent.TButton')
        self.run_button.pack(pady=20, ipadx=20, ipady=10)
        
        # Progress Bar 
        self.progress_bar = ttk.Progressbar(run_frame, orient='horizontal', length=400, mode='determinate', maximum=3)
        self.progress_bar.pack(pady=10)
        self.progress_bar.pack_forget() # Hide it initially
        
        # Done Message Label 
        self.done_label = ttk.Label(run_frame, text="✅ SYNC DONE! ✅", font=('Arial', 14, 'bold'), 
                                foreground='green', background='#e0ffe0', padding=10)
        self.done_label.pack_forget()

        # Output Console (Smaller)
        ttk.Label(run_frame, text="Live Output Console:", font=('Arial', 10, 'bold')).pack(pady=5, anchor='w')
        self.console_output = scrolledtext.ScrolledText(run_frame, wrap=tk.WORD, height=15, # Reduced height
                                                         bg='black', fg='lightgray', bd=0, relief="flat")
        self.console_output.pack(fill='both', expand=True)

    def append_to_console(self, text):
        """Appends text to the console output."""
        self.console_output.insert(tk.END, text + "\n")
        self.console_output.see(tk.END) # Auto-scroll to the bottom

    def start_sync_thread(self):
        """Starts the full sync process in a separate thread to keep the UI responsive."""
        self.run_button.config(state=tk.DISABLED, text="SYNC IN PROGRESS...")
        self.console_output.delete('1.0', tk.END)
        
        # Progress Bar Setup (NEW)
        self.progress_bar.pack(pady=10, after=self.run_button) # Show the progress bar
        self.progress_bar.config(value=0)
        
        # Hide the DONE message if restarting sync
        self.after(0, lambda: self.done_label.pack_forget())
        
        # Use a thread so the UI doesn't freeze during the long Selenium process
        sync_thread = threading.Thread(target=self.run_full_sync)
        sync_thread.start()

    def run_script_and_capture_output(self, script_name):
        """Helper to run a Python script and redirect its output to the console,
           and check for user prompt requests."""
        self.append_to_console(f"\n--- Running Stage: {script_name} ---")
        
        # Only implement interrupt/prompt logic for the Allocator script
        is_allocator = (script_name == ALLOCATOR_SCRIPT)
        
        try:
            # We use stdin=subprocess.PIPE for the allocator so we can send the input back
            stdin_pipe = subprocess.PIPE if is_allocator else None
            
            # Execute the script using the same Python interpreter
            process = subprocess.Popen(['python', script_name], 
                                         stdin=stdin_pipe,       # Added stdin pipe
                                         stdout=subprocess.PIPE, 
                                         stderr=subprocess.PIPE, 
                                         text=True, 
                                         bufsize=1) 
            
            # Pattern to detect the assignment group detection message
            assignment_pattern = re.compile(r"NEW ASSIGNMENT TYPE: '(.+?)'")

            # Read and display output line by line in real-time
            for line in process.stdout:
                
                # Check for the specific pattern if running the Allocator script
                if is_allocator:
                    match = assignment_pattern.search(line)
                    if match:
                        assignment_type = match.group(1)
                        
                        # Append the notification line to console
                        self.append_to_console(line.strip())
                        self.append_to_console("--- USER INPUT REQUIRED ---")
                        
                        # PAUSE EXECUTION and launch the prompt widget
                        user_time = self.prompt_for_time_estimate(assignment_type)

                        if user_time is None:
                            self.append_to_console("!!! User cancelled time allocation. Halting sync. !!!")
                            process.terminate()
                            return False
                        
                        # Send the user's input back to the allocator script via stdin
                        try:
                            time_str = str(user_time) + '\n'
                            process.stdin.write(time_str)
                            process.stdin.flush()
                            self.append_to_console(f"--- Sent input to script: {user_time} hours ---")
                        except Exception as write_error:
                            self.append_to_console(f"!!! Error sending input back: {write_error} !!!")
                            process.terminate()
                            return False

                # Append line to console after checking for pattern
                self.console_output.insert(tk.END, line)
                self.console_output.see(tk.END)
            
            # Close stdin pipe if it was opened
            if is_allocator:
                process.stdin.close()
                
            # Wait for the process to finish
            process.wait()

            # Check for errors from stderr
            stderr_output = process.stderr.read().strip()
            if stderr_output:
                self.append_to_console(f"!!! SCRIPT ERROR in {script_name} !!!\n{stderr_output}")
                return False 

            if process.returncode != 0:
                self.append_to_console(f"!!! SCRIPT FAILED: {script_name} exited with code {process.returncode} !!!")
                return False

            self.append_to_console(f"--- Stage {script_name} Complete (Code {process.returncode}) ---")
            return True

        except FileNotFoundError:
            self.append_to_console(f"ERROR: Python executable not found or script file '{script_name}' is missing.")
            return False
        except Exception as e:
            self.append_to_console(f"FATAL EXCEPTION running {script_name}: {e}")
            return False

    def update_run_tab_end_state(self, pipeline_success):
        """Handles final UI updates on the main thread after sync completion."""
        self.progress_bar.pack_forget()
        self.run_button.config(state=tk.NORMAL, text="▶ START FULL SYNC WORKFLOW")
        
        # Show the DONE message if successful
        if pipeline_success:
            # Repack the done label where the progress bar was
            self.done_label.pack(pady=10, after=self.run_button)
        # Note: If it failed, the done label remains hidden.


    def run_full_sync(self):
        """The main synchronization pipeline execution function."""
        pipeline_success = True
        
        # --- PRE-SYNC STEP: BACKUP SEEN_ASSIGNMENTS ---
        try:
            with open(SEEN_ASSIGNMENTS_FILE, 'r', encoding='utf-8') as src:
                content = src.read()
            with open(PREV_SEEN_ASSIGNMENTS_FILE, 'w', encoding='utf-8') as dst:
                dst.write(content)
            self.load_json_data(PREV_SEEN_ASSIGNMENTS_FILE)
            self.append_to_console("--- Backup: seen_assignments.json content successfully copied to prev_seen_assignments.json. (LITERAL COPY) ---")

        except FileNotFoundError:
            self.append_to_console("--- Backup: Source file seen_assignments.json not found, skipping content copy. ---")
        except Exception as e:
            self.append_to_console(f"WARNING: Failed to create backup of assignments (Pure Python Read/Write error): {e}")
            
        # 1. Canvas Scraper
        if pipeline_success:
            pipeline_success = self.run_script_and_capture_output(SCRAPER_SCRIPT)
            if pipeline_success:
                self.after(0, lambda: self.progress_bar.step(1))

        # 2. Time Allocator
        if pipeline_success:
            pipeline_success = self.run_script_and_capture_output(ALLOCATOR_SCRIPT)
            if pipeline_success:
                self.after(0, lambda: self.progress_bar.step(1))

        # --- Intermediary Popup Warning ---
        if pipeline_success:
            # Launch the pop-up on the main thread and wait for acknowledgment
            self.after(0, self.display_selenium_warning)
            self.continue_event.wait() 
            
            # Check if the user cancelled the pipeline via the window's close button
            if self.pipeline_cancelled:
                pipeline_success = False

        # 3. Reclaim Task Creator (Selenium automation)
        if pipeline_success:
            self.append_to_console("\n--- Starting Stage: RECLAIM TASK CREATOR (Selenium Automation) ---")
            self.append_to_console("A browser window will open now. DO NOT INTERACT with the browser until the script finishes.")
            pipeline_success = self.run_script_and_capture_output(RECLAIM_SCRIPT)
            if pipeline_success:
                self.after(0, lambda: self.progress_bar.step(1))

        # Final Status Update
        final_message = "✅ FULL SYNC WORKFLOW COMPLETED SUCCESSFULLY ✅" if pipeline_success else "❌ FULL SYNC WORKFLOW FAILED ❌"
        self.append_to_console(f"\n====================================\n{final_message}\n====================================")
        
        # Call the dedicated update function in the main thread
        self.after(0, self.update_run_tab_end_state, pipeline_success)


if __name__ == "__main__":
    app = SyncConfigApp()
    app.mainloop()