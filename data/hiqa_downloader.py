"""
HIQA Sample Report Downloader

Picks 50 random reports per year (2023-2026) from each link file,
downloads them with prefixed filenames:
  DIS_2023_centre-name-date.pdf
  NH_2024_centre-name-date.pdf

Setup:
    pip install requests

Usage:
    Put this script in the same folder as your two link files, then run:
    python hiqa_sample_downloader.py
"""

import os
import re
import random
import time
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.hiqa.ie/reports-and-publications/inspection-reports",
}

YEARS = [2023, 2024, 2025, 2026]
PER_YEAR = 50
OUTPUT_DIR = "hiqa_sample_reports"


def load_links(filepath):
    with open(filepath) as f:
        return [line.strip() for line in f if line.strip()]


def group_by_year(links):
    groups = {y: [] for y in YEARS}
    for url in links:
        for y in YEARS:
            if f"-{y}.pdf" in url:
                groups[y].append(url)
                break
    return groups


def download(session, url, prefix, output_dir, max_retries=3):
    match = re.search(r'inspectionreports/(.+\.pdf)', url)
    original_name = match.group(1) if match else url.split("/")[-1]

    # Extract year from filename
    year = "unknown"
    for y in YEARS:
        if f"-{y}.pdf" in original_name:
            year = str(y)
            break

    filename = f"{prefix}_{year}_{original_name}"
    filepath = os.path.join(output_dir, filename)

    if os.path.exists(filepath):
        return filename, True, "already exists"

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=60, stream=True)

            if resp.status_code in (429, 503):
                wait = attempt * 15
                print(f"    Rate limited, waiting {wait}s (attempt {attempt}/{max_retries})")
                time.sleep(wait)
                continue

            resp.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filename, True, None

        except Exception as e:
            if attempt < max_retries:
                time.sleep(attempt * 10)
            else:
                return filename, False, str(e)

    return filename, False, "Max retries exceeded"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Define the two sources
    sources = [
        ("hiqa_disability_report_links.txt", "DIS"),
        ("hiqa_nursing_home_report_links.txt", "NH"),
    ]

    session = requests.Session()

    # Warm up session
    print("Warming up session...")
    try:
        r = session.get(
            "https://www.hiqa.ie/reports-and-publications/inspection-reports",
            headers=HEADERS, timeout=30
        )
        print(f"  Status: {r.status_code}")
        if r.status_code == 429:
            print("  Still rate limited! Wait a few more minutes and try again.")
            return
    except Exception as e:
        print(f"  Warning: {e}")

    total_to_download = 0
    download_queue = []

    for links_file, prefix in sources:
        if not os.path.exists(links_file):
            print(f"Skipping {links_file} — file not found")
            continue

        links = load_links(links_file)
        groups = group_by_year(links)

        print(f"\n{prefix} ({links_file}):")
        for year in YEARS:
            available = len(groups[year])
            pick = min(PER_YEAR, available)
            sample = random.sample(groups[year], pick)
            download_queue.extend([(url, prefix) for url in sample])
            print(f"  {year}: picking {pick} from {available} available")
            total_to_download += pick

    print(f"\nTotal to download: {total_to_download} reports")
    print(f"Estimated time: ~{total_to_download * 2 // 60} minutes")
    print(f"Saving to: {OUTPUT_DIR}/")
    print()

    random.shuffle(download_queue)  # Mix them up to spread load across years

    success = 0
    failed = 0
    skipped = 0

    for i, (url, prefix) in enumerate(download_queue, 1):
        filename, ok, err = download(session, url, prefix, OUTPUT_DIR)

        if ok:
            if err == "already exists":
                skipped += 1
            else:
                success += 1
        else:
            failed += 1
            print(f"  FAILED: {filename} — {err}")

        if i % 25 == 0 or i == len(download_queue):
            print(f"  Progress: {i}/{len(download_queue)}  (ok: {success}, skipped: {skipped}, failed: {failed})")

        if err != "already exists":
            time.sleep(2)

    print(f"\nDone! {success} downloaded, {skipped} already existed, {failed} failed.")
    print(f"Files are in: {OUTPUT_DIR}/")
    print(f"  DIS_YYYY_*.pdf = Disability service reports")
    print(f"  NH_YYYY_*.pdf  = Nursing home reports")


if __name__ == "__main__":
    main()
    