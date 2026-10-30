import sys
import json
from listing_agent import create_listing_draft

if len(sys.argv) < 2:
    print("Usage: python run_cli.py photo.jpg \"details about the item\"")
    sys.exit(1)

photo_path = sys.argv[1]
details = sys.argv[2] if len(sys.argv) > 2 else "No extra details"

with open(photo_path, "rb") as f:
    draft = create_listing_draft(f.read(), details)

print(json.dumps(draft, indent=2))