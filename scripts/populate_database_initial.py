"""
Script to scrape historical figure names from Google Arts & Culture,
save them to backend/initial_figures.txt, and populate the database
with detailed information about each figure in parallel.

Usage:
    # Just scrape names (no database population)
    uv run python populate_database_initial.py --scrape-only

    # Populate database from existing file (no scraping)
    uv run python populate_database_initial.py --populate-only

    # Clean invalid names from database
    uv run python populate_database_initial.py --clean

    # Do both scraping and population (default)
    uv run python populate_database_initial.py
"""

import argparse
import multiprocessing
import os
import re
import json
import requests
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore


def is_valid_name(name: str) -> bool:
    """
    Determine if a string is likely a valid historical figure name.
    Returns False for data artifacts, IDs, and generic labels.
    """
    name = name.strip()

    # Skip empty lines
    if not name:
        return False

    # Skip encoded/hashed data (base64-like strings starting with Ck, Cl, Cm, etc.)
    # Base64 uses: A-Z, a-z, 0-9, +, /, =
    if re.match(r'^C[a-zA-Z][a-zA-Z0-9+/=]{20,}$', name):
        return False

    # Skip asset references with UUIDs
    if any(prefix in name for prefix in ['DatedAssets:', 'PrefixedAssets:', 'PopularAssets:']):
        return False

    # Skip time periods
    if re.match(r'^\d+BCE$', name):
        return False

    # Skip generic/site labels
    generic_labels = {
        'Present',
        'Untitled',
        'Historical Figures',
        'Google Arts & Culture',
        'historical-figure',
        'Explore all historical figures on Google Arts & Culture.',
    }
    if name in generic_labels:
        return False

    # Skip very short names (likely artifacts)
    if len(name) < 2:
        return False

    # Skip names that are mostly numbers
    if sum(c.isdigit() for c in name) / len(name) > 0.5:
        return False

    # Skip if it looks like a UUID pattern
    if re.search(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', name):
        return False

    # Skip if it contains only special characters and numbers (no letters)
    if not any(c.isalpha() for c in name):
        return False

    return True


def fetch_historical_figures():
    """Fetch and parse historical figures from Google Arts & Culture"""
    url = "https://artsandculture.google.com/category/historical-figure"

    print(f"Fetching {url}...")
    response = requests.get(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })
    response.raise_for_status()

    html = response.text
    print(f"Received {len(html)} characters")

    # Find the INIT_data JavaScript object
    # Pattern: window.INIT_data['Category:...'] = [...]
    pattern = r"window\.INIT_data\['Category:[^']+'\]\s*=\s*(\[[\s\S]*?\]);?\s*(?:window\.INIT_data|</script>)"

    matches = re.findall(pattern, html)

    if not matches:
        print("Could not find INIT_data in page")
        return []

    print(f"Found {len(matches)} data structures")

    names = set()

    for match in matches:
        try:
            # Parse the JavaScript array as JSON
            data = json.loads(match)

            # The data structure appears to be an array with nested elements
            # We need to find strings that look like names (not URLs, not numbers)
            def extract_names(obj):
                """Recursively extract potential names from data structure"""
                if isinstance(obj, str):
                    # Skip URLs, IDs, and other non-name strings
                    if not any(skip in obj.lower() for skip in ['http', '/', 'items', 'stella.', 'category']):
                        # Skip very short strings and strings with only numbers
                        if len(obj) > 3 and not obj.isdigit() and not obj.startswith('['):
                            # Check if it looks like a name (contains letters)
                            if any(c.isalpha() for c in obj):
                                return [obj]
                elif isinstance(obj, list):
                    results = []
                    for item in obj:
                        results.extend(extract_names(item))
                    return results
                elif isinstance(obj, dict):
                    results = []
                    for value in obj.values():
                        results.extend(extract_names(value))
                    return results
                return []

            extracted = extract_names(data)
            names.update(extracted)

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            continue

    # Filter out invalid names
    all_names = sorted(list(names))
    valid_names = [name for name in all_names if is_valid_name(name)]

    print(f"Extracted {len(all_names)} total names")
    print(f"Filtered to {len(valid_names)} valid names ({len(all_names) - len(valid_names)} removed)")

    return valid_names


def process_single_person_initial(name: str):
    """
    Function to be run in a separate process.
    Processes one historical figure with initial=True flag.
    """
    try:
        from backend.agent import StoryGeneratorAgent
        agent = StoryGeneratorAgent()
        agent.process_person(name, initial=True)
        return f"Success: {name}"
    except Exception as e:
        return f"Error processing {name}: {e}"


def populate_database(names: list[str], max_workers: int = None):
    """
    Populate the database with historical figures in parallel.

    Args:
        names: List of names to process
        max_workers: Number of parallel workers (default: CPU count)
    """
    if max_workers is None:
        max_workers = multiprocessing.cpu_count()

    print(f"\n{'='*60}")
    print(f"Starting database population with {max_workers} workers")
    print(f"Processing {len(names)} figures")
    print(f"{'='*60}\n")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for name in names:
            print(f"Submitting task for: {name}")
            future = executor.submit(process_single_person_initial, name)
            futures.append((name, future))

        # Monitor completion
        completed = 0
        total = len(futures)
        for name, future in futures:
            try:
                result = future.result()
                completed += 1
                print(f"[{completed}/{total}] {result}")
            except Exception as e:
                completed += 1
                print(f"[{completed}/{total}] Task exception for {name}: {e}")

    print(f"\n{'='*60}")
    print(f"Database population complete!")
    print(f"Processed {completed}/{total} figures")
    print(f"{'='*60}\n")


def scrape_figures():
    """Scrape figures and save to file."""
    figures = fetch_historical_figures()

    if figures:
        # Show first few examples
        print("\nFirst 10 cleaned names:")
        for name in figures[:10]:
            print(f"  - {name}")

        # Create backend directory if it doesn't exist
        backend_dir = Path("backend")
        backend_dir.mkdir(exist_ok=True)

        # Save to file
        output_file = backend_dir / "initial_figures.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            for name in figures:
                f.write(f"{name}\n")

        print(f"\nSaved {len(figures)} cleaned names to {output_file}")
        return figures
    else:
        print("No names found!")
        return []


def load_figures_from_file():
    """Load figure names from the saved file."""
    figures_file = Path("backend/initial_figures.txt")

    if not figures_file.exists():
        print(f"Error: {figures_file} does not exist. Run with --scrape-only first.")
        return []

    with open(figures_file, 'r', encoding='utf-8') as f:
        names = [line.strip() for line in f if line.strip()]

    print(f"Loaded {len(names)} names from {figures_file}")
    return names


def clean_invalid_names_from_db():
    """Find and remove invalid names from the database."""
    # Initialize Firebase
    cred_path = os.path.expanduser("~/firebase-keys/kindred-histories-firebase-key.json")

    if os.path.exists(cred_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
        print(f"Using credentials from {cred_path}")
    elif os.path.exists("service-account-key.json"):
        cred_path = "service-account-key.json"
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
        print(f"Using credentials from {cred_path}")
    else:
        print("Error: No Firebase credentials found!")
        return

    # Initialize Firebase app if not already initialized
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            print("Firebase initialized successfully")
        except Exception as e:
            print(f"Failed to initialize Firebase: {e}")
            return

    # Get Firestore client
    try:
        db = firestore.client()
        print("Connected to Firestore database")
    except Exception as e:
        print(f"Firestore client creation failed: {e}")
        return

    # Get all documents in the collection
    collection_ref = db.collection("historical_figures")
    docs = collection_ref.stream()

    # Separate valid from invalid names
    doc_list = list(docs)
    valid_docs = []
    invalid_docs = []

    print(f"\nScanning {len(doc_list)} documents...")

    for doc in doc_list:
        data = doc.to_dict()
        name = data.get("name", "")

        if is_valid_name(name):
            valid_docs.append((doc, name))
        else:
            invalid_docs.append((doc, name))

    print(f"\n{'='*60}")
    print(f"Scan Results:")
    print(f"  Valid names: {len(valid_docs)}")
    print(f"  Invalid names: {len(invalid_docs)}")
    print(f"{'='*60}\n")

    if not invalid_docs:
        print("No invalid names found in the database!")
        return

    # Show invalid names
    print("Invalid names found:")
    for i, (doc, name) in enumerate(invalid_docs[:20], 1):
        # Truncate very long names
        display_name = name[:80] + "..." if len(name) > 80 else name
        print(f"  {i}. {display_name}")

    if len(invalid_docs) > 20:
        print(f"  ... and {len(invalid_docs) - 20} more")

    print()
    response = input(f"Delete these {len(invalid_docs)} invalid entries? (yes/no): ")

    if response.lower() != "yes":
        print("Deletion cancelled.")
        return

    # Delete invalid documents
    print("\nDeleting invalid documents...")
    deleted_count = 0

    for doc, name in invalid_docs:
        try:
            doc.reference.delete()
            deleted_count += 1
            if deleted_count % 10 == 0:
                print(f"  Deleted {deleted_count}/{len(invalid_docs)} documents...")
        except Exception as e:
            print(f"  Error deleting {doc.id}: {e}")

    print(f"\n{'='*60}")
    print(f"✓ Successfully deleted {deleted_count} invalid entries")
    print(f"✓ Preserved {len(valid_docs)} valid entries")
    print(f"{'='*60}")


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Scrape and populate initial historical figures")
    parser.add_argument("--scrape-only", action="store_true", help="Only scrape names, don't populate database")
    parser.add_argument("--populate-only", action="store_true", help="Only populate database from existing file")
    parser.add_argument("--clean", action="store_true", help="Clean invalid names from database")
    parser.add_argument("--limit", type=int, help="Limit number of figures to process (for testing)")
    parser.add_argument("--workers", type=int, help="Number of parallel workers")

    args = parser.parse_args()

    if args.clean:
        # Clean invalid names from database
        clean_invalid_names_from_db()
    elif args.scrape_only:
        # Just scrape
        scrape_figures()
    elif args.populate_only:
        # Just populate from existing file
        names = load_figures_from_file()
        if names:
            if args.limit:
                names = names[:args.limit]
                print(f"Limited to first {args.limit} figures for testing")
            populate_database(names, max_workers=args.workers)
    else:
        # Do both
        figures = scrape_figures()
        if figures:
            if args.limit:
                figures = figures[:args.limit]
                print(f"Limited to first {args.limit} figures for testing")
            populate_database(figures, max_workers=args.workers)


if __name__ == "__main__":
    main()
