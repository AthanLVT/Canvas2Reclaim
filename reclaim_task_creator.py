import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys

# --- 1. LOAD CONFIG ---
try:
    import config
    RECLAIM_EMAIL = config.RECLAIM_EMAIL
    RECLAIM_PASSWORD = config.RECLAIM_PASSWORD
    CHROME_PROFILE_PATH = config.CHROME_PROFILE_PATH
    CHROME_PROFILE_NAME = config.CHROME_PROFILE_NAME

    if not all([RECLAIM_EMAIL, RECLAIM_PASSWORD, CHROME_PROFILE_PATH]):
        print("ERROR: Missing critical configuration in config.py.")
        exit()
except Exception as e:
    print(f"FATAL ERROR: Could not load config.py: {e}")
    exit()

# --- 2. LOAD LOCAL JSON FILES ---
def load_json_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        print(f"ERROR: File {filename} contains invalid JSON.")
        return []

def save_json_file(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"ERROR: Could not save {filename}: {e}")

NEW_ASSIGNMENTS = load_json_file('new_assignment_names.json')
TIMED_ASSIGNMENTS = load_json_file('timed_assignments.json')

tasks_to_sync = [
    task for task in TIMED_ASSIGNMENTS 
    if not task.get('reclaim_synced', False) 
    and task.get('time_allocated_hours')
    and any(task['name'] == n['name'] for n in NEW_ASSIGNMENTS)
]

if not tasks_to_sync:
    print("No new tasks to sync.")
    exit()

print(f"Found {len(tasks_to_sync)} tasks to sync.")

# --- 3. SELENIUM SETUP ---
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument(f"user-data-dir={CHROME_PROFILE_PATH}")
    chrome_options.add_argument(f"profile-directory={CHROME_PROFILE_NAME}")
    chrome_options.add_argument("--start-maximized")
    # Disable unnecessary delays
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-gpu")

    service = Service(ChromeDriverManager().install())
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print(f"ERROR: Chrome failed to start. {e}")
        exit()

driver = setup_driver()
# REDUCE GLOBAL WAIT TIME FROM 20 TO 10 SECONDS FOR FASTER INTERACTIONS
wait = WebDriverWait(driver, 10) 
total_synced = 0

# --- 4. RECLAIM LOGIN ---
def reclaim_login(driver):
    driver.get("https://app.reclaim.ai/planner")
    print("Logging into Reclaim...")

    try:
        # Check for login form (if not already logged in)
        email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        email_field.send_keys(RECLAIM_EMAIL)
        password_field = driver.find_element(By.NAME, "password")
        password_field.send_keys(RECLAIM_PASSWORD)
        login_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Log in')]")
        login_button.click()
        # Wait for planner to load
        wait.until(EC.presence_of_element_located((By.ID, "QuickCreateTask")))
    except Exception:
        # Already logged in
        wait.until(EC.presence_of_element_located((By.ID, "QuickCreateTask")))
        print("Already logged in.")

# --- 5. CREATE TASK FUNCTION ---
def create_reclaim_task(task):
    global total_synced

    # Click "New Task" button
    # This uses the new, shorter 'wait' object (10 seconds), 
    # which should solve the 20-second delay.
    wait.until(EC.element_to_be_clickable((By.ID, "QuickCreateTask"))).click() 
    print("Clicked New Task button.")

    # 1. Task Title
    task_title_input = wait.until(
        EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Task name...']"))
    )
    task_name = f"[Canvas] {task['name']}"
    task_title_input.send_keys(task_name)
    print(f" Task Name entered: {task_name}")

    # 2. Duration (Robust Clear)
    try:
        duration_input = wait.until(
            EC.presence_of_element_located((By.NAME, "durationMs"))
        )
        duration_input.click()
        duration_input.send_keys(Keys.CONTROL + "a")
        duration_input.send_keys(Keys.DELETE)
        duration_input.send_keys(str(task['time_allocated_hours']))
        print(f" Duration entered: {task['time_allocated_hours']} hours")
    except Exception as e:
        print(f"WARNING: Failed to find/fill Duration input. Error: {e}")

    # 3. Schedule After / Start Date
    if task.get('start_at'):
        try:
            start_input = wait.until(
                EC.presence_of_element_located((By.NAME, "snoozeUntil"))
            )
            start_input.click()
            start_input.send_keys(Keys.CONTROL + "a")
            start_input.send_keys(Keys.DELETE)
            start_input.send_keys(task['start_at'])
            print(f" Start Date entered: {task['start_at']}")
        except Exception as e:
            print(f"WARNING: Failed to find/fill Start Date input. Error: {e}")

    # 4. Due Date
    if task.get('due_at'):
        try:
            due_date_input = wait.until(
                EC.presence_of_element_located((By.NAME, "due"))
            )
            due_date_input.click()
            due_date_input.send_keys(Keys.CONTROL + "a")
            due_date_input.send_keys(Keys.DELETE)
            due_date_input.send_keys(task['due_at'])
            print(f" Due Date entered: {task['due_at']}")
        except Exception as e:
            print(f"WARNING: Failed to find/fill Due Date input. Error: {e}")

    # 5. Click safe spot inside form to close date pickers
    try:
        form_safe_area = driver.find_element(By.CSS_SELECTOR, "div.AddTaskForm_section__zJF4U")
        form_safe_area.click()
        time.sleep(0.1)
    except Exception as e:
        print(f"WARNING: Could not click safe area. Error: {e}")

    # 6. Click 'Create' Button and press ESC immediately after
    try:
        create_button = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[@aria-label='Create task' or span[text()='Create']]")
            )
        )
        create_button.click()
        
        # Press ESC immediately after clicking Create
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ESCAPE)
            time.sleep(0.1)
        except:
            pass

        # Wait until modal closes
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//input[@placeholder='Task name...']")))
        print(f" Task successfully created: {task_name}")

        task['reclaim_synced'] = True
        total_synced += 1
    except Exception as e:
        print(f"FAILURE: Could not create task '{task['name']}': {e}")
        # Attempt to close failed modal
        try:
            close_button = driver.find_element(By.XPATH, "//button[@aria-label='Close']")
            close_button.click()
            wait.until(EC.invisibility_of_element_located((By.XPATH, "//input[@placeholder='Task name...']")))
            print("Attempted to close failed modal.")
        except:
            pass

# --- 6. MAIN EXECUTION ---
def main():
    reclaim_login(driver)
    for task in tasks_to_sync:
        try:
            create_reclaim_task(task)
            time.sleep(1)
        except Exception as e:
            print(f"FAILURE: Could not create task '{task['name']}': {e}")

    save_json_file('timed_assignments.json', TIMED_ASSIGNMENTS)
    driver.quit()
    print(f"\n--- Sync Complete ---\nTotal tasks synced: {total_synced}")

if __name__ == "__main__":
    main()