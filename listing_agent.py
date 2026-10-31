
import os
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Look for .env next to this file, even if you run the app from another folder.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# The AI model. If you get a "not found" or "limit" error, change this one line
# to "gemini-3.5-flash-lite" (also listed with a free tier).
MODEL = "gemini-3.8-flash"

# OPTIONAL backup model. Leave it as "" (empty) to use only MODEL.
# If you want a backup when Google says "503 busy", set it to
# "gemini-3.5-flash-lite". It is tried ONLY after MODEL is still busy
# (503) after its retries. It is never used for limit errors (429).
FALLBACK_MODEL = ""

# How long to wait between tries when Google says 503 (busy):
# try 1 -> wait 3s -> try 2 -> wait 8s -> try 3 -> give up.
BUSY_WAITS = (3, 8)

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


def _error_code(error):
    """Return the HTTP code from a Gemini error (503, 429, ...) or None."""
    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code
    text = str(error)
    if "503" in text or "UNAVAILABLE" in text:
        return 503
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return 429
    return None


def _call_gemini(model, instruction, image_bytes, details, mime):
    """One request to Gemini with one model."""
    response = get_client().models.generate_content(
        model=model,
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


def ask_ai(instruction, image_bytes, details, mime="image/jpeg"):
    """Send photo + details to Gemini and return the text answer.
    - 503 (Google is busy): wait a few seconds and try again (max 3 tries),
      then try FALLBACK_MODEL the same way if you set one.
    - 429 (free limit hit): wait and try again on the SAME model, never switch.
    - Any other error: stop at once and explain."""
    models = [MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != MODEL:
        models.append(FALLBACK_MODEL)

    last_error = None
    for model in models:
        tries = len(BUSY_WAITS) + 1
        for attempt in range(tries):
            try:
                return _call_gemini(model, instruction, image_bytes, details, mime)
            except Exception as error:  # keep it simple: retry, then explain
                last_error = error
                code = _error_code(error)
                if code == 429:
                    # Free limit: same model only, wait 20s then 40s.
                    if attempt < 2:
                        time.sleep(20 * (attempt + 1))
                        continue
                    raise RuntimeError(f"Gemini call failed: {last_error}")
                if code == 503:
                    if attempt < tries - 1:
                        time.sleep(BUSY_WAITS[attempt])
                    continue  # after the last try, the next model (if any)
                raise RuntimeError(f"Gemini call failed: {error}")
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
