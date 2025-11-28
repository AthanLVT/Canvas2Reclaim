import os
import json
import sys
import requests
from datetime import datetime, timedelta
from config import CANVAS_URL, CANVAS_TOKEN, RECLAIM_API_KEY  # <- load from config.py

SEEN_FILE = "seen_assignments.json"

# --- SAFETY CHECKS ---
if not CANVAS_TOKEN:
    print("ERROR: CANVAS_TOKEN is missing. Please update your config.py file.")
    sys.exit(1)

if not CANVAS_URL:
    print("ERROR: CANVAS_URL is missing.")
    sys.exit(1)

# --- HELPER FUNCTIONS ---
def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {SEEN_FILE} is corrupted. Starting with an empty list.")
            return []
    return []

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=2)

def save_new_names_only(new_assignments: list):
    NEW_NAMES_FILE = "new_assignment_names.json"
    names_and_details = [
        {
            "name": a.get("name"),
            "course": a.get("course_name", "Unknown"), 
            "link": a.get("html_url")
        } 
        for a in new_assignments
    ]
    with open(NEW_NAMES_FILE, "w") as f:
        json.dump(names_and_details, f, indent=2)

# --- FETCH ASSIGNMENTS ---
def fetch_assignments():
    headers = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
    all_assignments = []

    courses_url = f"{CANVAS_URL}/api/v1/courses?per_page=100&enrollment_state=active"
    print("Fetching active course IDs...")

    try:
        response = requests.get(courses_url, headers=headers)
        response.raise_for_status()
        courses = response.json()
    except requests.exceptions.RequestException as e:
        print(f"FATAL ERROR: Could not fetch courses. Error: {e}")
        return []

    print(f"Found {len(courses)} active courses. Fetching assignments...")

    for course in courses:
        course_id = course.get("id")
        course_name = course.get("name", "Unknown Course")
        if not course_id:
            continue
        assignments_url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments"
        params = {"bucket": "unsubmitted", "order_by": "due_at", "per_page": 50}

        try:
            assignment_response = requests.get(assignments_url, headers=headers, params=params)
            assignment_response.raise_for_status()
            course_assignments = assignment_response.json()
            for assignment in course_assignments:
                assignment["course_name"] = course_name
                all_assignments.append(assignment)
            print(f"  Fetched {len(course_assignments)} assignments for {course_name}")
        except requests.exceptions.RequestException:
            continue

    return all_assignments

# --- RECLAIM TASK CREATION ---
def create_reclaim_task(title, due_date_iso, link):
    if not RECLAIM_API_KEY:
        print(f"Skipping Reclaim sync for {title}: No API Key found.")
        return
    url = "https://api.reclaim.ai/api/tasks"
    headers = {
        "Authorization": f"Bearer {RECLAIM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "title": f"Assignment: {title}",
        "dueDate": due_date_iso,
        "duration": 60,
        "priority": "DEFAULT",
        "notes": f"Canvas Link: {link}",
        "alwaysPrivate": True
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            print(f"Added to Reclaim: {title}")
        else:
            print(f"Failed to add to Reclaim (Status {response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Reclaim API: {e}")

# --- MAIN SCRIPT ---
def main():
    seen_assignments = load_seen()
    seen_links = {a['html_url'] for a in seen_assignments if 'html_url' in a} 
    new_assignments = []

    events = fetch_assignments()
    print(f"\nFound {len(events)} total potential assignments. Filtering...")

    for ev in events:
        name = ev.get("name")
        link = ev.get("html_url")
        due_date = ev.get("due_at")
        open_date = ev.get("unlock_at")
        course_name = ev.get("course_name", "Unknown")
        if not link or not name or not due_date:
            continue
        assignment_data = {
            "name": name,
            "html_url": link,
            "course_name": course_name,
            "due_at": due_date,
            "unlock_at": open_date
        }
        if link not in seen_links:
            new_assignments.append(assignment_data)
            seen_assignments.append(assignment_data)
            seen_links.add(link)
            reclaim_title = f"[{course_name}] {name}"
            print(f"Ready to sync NEW assignment: {reclaim_title}. (Due: {due_date})")
            # create_reclaim_task(reclaim_title, due_date, link)

    save_seen(seen_assignments)
    save_new_names_only(new_assignments)
    
    if new_assignments:
        print(f"Saved {len(new_assignments)} new assignment names to new_assignment_names.json.")
    else:
        print("No new assignments found. Cleared new_assignment_names.json.")

    print("\n" + "=" * 50)
    print(f"COMPLETE: Found {len(new_assignments)} new assignments.")
    print(f"Total assignments tracked: {len(seen_assignments)}")
    print("=" * 50)

if __name__ == "__main__":
    main()
