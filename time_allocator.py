import json
import os
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional

# --- Configuration ---
SEEN_FILE = "seen_assignments.json"
RULES_FILE = "assignment_time_rules.json"
TIMED_FILE = "timed_assignments.json"
SIMILARITY_THRESHOLD = 0.50 # 50% similarity threshold for grouping names

# --- Helper Functions ---

def load_json(filename: str) -> Any:
    """Loads JSON data from a file."""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {filename} is corrupted. Starting empty.")
            return {} if filename == RULES_FILE else []
    return {} if filename == RULES_FILE else []

def save_json(filename: str, data: Any):
    """Saves data to a JSON file."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_similarity_group_key(assignment_name: str, existing_rules: Dict[str, Any]) -> Optional[str]:
    """
    Compares a new assignment name against existing rule keys using SequenceMatcher.
    Returns the key of the matching group if similarity exceeds the threshold.
    """
    cleaned_name = assignment_name.lower().strip()
    
    # Check against existing group keys
    for group_key in existing_rules.keys():
        # Use SequenceMatcher for character-order-aware similarity
        ratio = SequenceMatcher(None, cleaned_name, group_key).ratio()
        
        if ratio >= SIMILARITY_THRESHOLD:
            # We found a match, return the existing group key
            return group_key
            
    # No similar group found
    return None

def get_time_from_user(group_name: str) -> float:
    """Prompts the user for the time taken for a new assignment group."""
    while True:
        try:
            prompt = f"\n NEW ASSIGNMENT TYPE: '{group_name}'\n   Enter time to complete (in hours, e.g., 1.5): "
            user_input = input(prompt)
            time_taken = float(user_input)
            if time_taken <= 0:
                print("Time must be greater than 0.")
                continue
            return time_taken
        except ValueError:
            print("Invalid input. Please enter a number.")

# --- Main Logic ---

def allocate_time():
    """
    Reads assignments, groups them by name similarity, and allocates time.
    """
    print("--- Time Allocator Running ---")
    
    # Load data
    assignments: List[Dict[str, Any]] = load_json(SEEN_FILE)
    time_rules: Dict[str, Any] = load_json(RULES_FILE)
    timed_assignments: List[Dict[str, Any]] = []

    if not assignments:
        print("No assignments found in seen_assignments.json. Exiting.")
        return

    # 1. Group Assignments and Update Rules
    for assignment in assignments:
        assignment_name = assignment.get("name", "Unnamed Assignment")
        
        # Check if the name belongs to an existing group
        group_key = get_similarity_group_key(assignment_name, time_rules)

        if group_key:
            # Found an existing group
            assignment["group_key"] = group_key
        else:
            # New assignment type found: create a new group and ask for time
            print(f"\n--- New Assignment Group Detected ---")
            
            # Use the assignment name itself as the initial group key
            new_group_key = assignment_name
            
            # Check if we already have a time rule for this specific new name (in case the similarity missed it)
            if new_group_key not in time_rules or time_rules[new_group_key].get("time_taken") is None:
                
                # Ask user for time
                time_taken = get_time_from_user(new_group_key)
                
                # Store the new rule
                time_rules[new_group_key] = {
                    "group_key": new_group_key,
                    "time_taken": time_taken
                }
                
                print(f"   Rule saved: '{new_group_key}' set to {time_taken} hours.")

            assignment["group_key"] = new_group_key
    
    # Save the updated rules file
    save_json(RULES_FILE, time_rules)
    print("\n Assignment time rules updated.")

    # 2. Assign Time and Create New List
    for assignment in assignments:
        group_key = assignment.get("group_key")
        time_rule = time_rules.get(group_key)

        if time_rule and time_rule.get("time_taken") is not None:
            time_taken = time_rule["time_taken"]
            
            # Create the new dictionary with original data and time attached
            timed_item = assignment.copy() # Start with all original data
            timed_item["time_allocated_hours"] = time_taken
            timed_assignments.append(timed_item)
        else:
            # Should not happen if logic is correct, but handles a missing rule
            print(f"Warning: Could not assign time to '{assignment.get('name')}' (Missing rule). Skipping.")
            
    
    # 3. Save the final list
    save_json(TIMED_FILE, timed_assignments)
    print(f"\n Successfully processed {len(timed_assignments)} assignments.")
    print(f"   Data saved to {TIMED_FILE}")


if __name__ == "__main__":
    allocate_time()