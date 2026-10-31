import os
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Look for .env next to this file, even if you run the app from another folder.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# The AI model. If you get a "not found" or "limit" error, change this one line
# to "gemini-3.5-flash-lite" (also free).
MODEL = "gemini-3.8-flash"

CATEGORIES = [
    "Electronics", "Fashion", "Home & Kitchen", "Books",
    "Toys & Games", "Sports", "Beauty", "Collectibles", "Other",
]

SYSTEM_RULES = (
    "You are a marketplace listing assistant. "
    "Only describe what is visible in the photo or "
    "stated in the seller details. Never invent facts."
)

_client = None


def get_client():
    """Create the Gemini client the first time we need it."""
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY not found. Check that your .env file is in the "
                "same folder as app.py and has the line GEMINI_API_KEY=your-key")
        _client = genai.Client(api_key=key)
    return _client


def ask_ai(instruction, image_bytes, details, mime="image/jpeg"):
    """Send photo + details to Gemini and return the text answer.
    If the free limit is hit (error 429), wait a little and try again."""
    last_error = None
    for attempt in range(3):
        try:
            response = get_client().models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime),
                    f"Seller details: {details}\n\n{instruction}",
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_RULES,
                    response_mime_type="application/json",
                ),
            )
            return (response.text or "").strip()
        except Exception as error:  # keep it simple: retry, then explain
            last_error = error
            if "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                time.sleep(20 * (attempt + 1))   # wait 20s, then 40s
            else:
                break
    raise RuntimeError(f"Gemini call failed: {last_error}")


def clean_price(price):
    """Safety check: price must be an object with min, max and reason."""
    fallback = {"min": None, "max": None, "reason": "Could not suggest a price"}
    if not isinstance(price, dict):
        return fallback
    if not all(key in price for key in ("min", "max", "reason")):
        return fallback
    return price


def create_listing_draft(image_bytes, details, mime="image/jpeg"):
    """ONE Gemini call makes the whole draft (fewer calls = fewer limit errors)."""
    options = ", ".join(CATEGORIES)
    raw = ask_ai(
        "Create a listing draft. Return only JSON with these keys: "
        '"title" (max 70 characters, include brand and key feature if known), '
        '"description" (3-5 short lines: condition, features, what is included), '
        f'"category" (exactly one of: {options}), '
        '"price_range" (fair resale price in INR, like '
        '{"min": 500, "max": 800, "reason": "short reason"}).',
        image_bytes, details, mime)

    # If the AI answer is not usable, we raise an error on purpose.
    # app.py then shows "AI failed" and opens the blank manual form.
    try:
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("The AI answer was not valid JSON")
    if not isinstance(data, dict) or not data.get("title"):
        raise RuntimeError("The AI answer had no title")

    category = data.get("category")
    return {
        "title": str(data.get("title") or "").strip(),
        "description": str(data.get("description") or "").strip(),
        "category": category if category in CATEGORIES else "Other",
        "price_range": clean_price(data.get("price_range")),
        "status": "DRAFT - waiting for seller approval",
    }


# Small helpers kept so older files (run_cli.py) still work.
def generate_title(image_bytes, details, mime="image/jpeg"):
    return create_listing_draft(image_bytes, details, mime)["title"]


def generate_description(image_bytes, details, mime="image/jpeg"):
    return create_listing_draft(image_bytes, details, mime)["description"]


def suggest_category(image_bytes, details, mime="image/jpeg"):
    return create_listing_draft(image_bytes, details, mime)["category"]


def suggest_price_range(image_bytes, details, mime="image/jpeg"):
    return create_listing_draft(image_bytes, details, mime)["price_range"]
