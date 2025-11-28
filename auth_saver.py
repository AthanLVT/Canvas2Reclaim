import os
import sys 
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
RECLAIM_LOGIN_URL = os.getenv("RECLAIM_LOGIN_URL") 
STORAGE_STATE_PATH = "auth.json"
USER_DATA_DIR = "./user_data" # Directory to store persistent browser profile

def save_auth_state():
    """Launches browser with a persistent context for manual login and saves the session state."""
    
    if not RECLAIM_LOGIN_URL or RECLAIM_LOGIN_URL.startswith("https://accounts.google.com"):
        print("❌ ERROR: RECLAIM_LOGIN_URL must be the Reclaim login URL (https://app.reclaim.ai/login).")
        sys.exit(1) 

    if os.path.exists(STORAGE_STATE_PATH):
        print(f"Warning: '{STORAGE_STATE_PATH}' already exists. Delete it before running if you need a new login.")
        return

    print("--- AUTHENTICATION SAVER ---")
    print("1. Launching browser with a persistent profile. This may help bypass security checks.")
    print("2. The script will click 'Continue with Google' and then wait for you to log in.")
    print("3. Please complete the Google sign-in process in the new window.")
    
    with sync_playwright() as p:
        # Use a persistent context. This simulates a regular, non-incognito browser.
        # This is the key change to bypass the security message.
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, 
            headless=False,
            slow_mo=50
        )
        page = context.new_page()

        print(f"Navigating to {RECLAIM_LOGIN_URL} to get context...")
        page.goto(RECLAIM_LOGIN_URL)
        
        # Click the "Continue with Google" button
        try:
            page.click("button:has-text('Continue with Google')") 
        except Exception as e:
            print(f"❌ Could not click 'Continue with Google' button. Check the selector. Error: {e}")
            context.close()
            sys.exit(1)


        # We wait until the URL is the Reclaim inbox/dashboard, indicating successful redirection
        try:
            print("\nWaiting for successful redirection to Reclaim.ai Inbox (Max 60 seconds)...")
            page.wait_for_url("**/inbox", timeout=60000) 
            
            # --- SUCCESS ---
            print("\n✅ Successfully landed on Reclaim.ai Inbox.")
            print(f"4. Saving authentication state to {STORAGE_STATE_PATH}")
            
            # Save the session cookies, local storage, etc.
            context.storage_state(path=STORAGE_STATE_PATH)
            print("✅ Authentication state saved successfully. You can now close the browser.")
            
        except Exception as e:
            print(f"\n❌ Login failed or timed out. State was NOT saved. Error: {e}")
            
        context.close()

if __name__ == "__main__":
    save_auth_state()