# app.py - version 3: cleaner design (photo left, details right, live preview card)
# Works with the SAME listing_agent.py (Gemini version) you already have.
# Nothing else changes: .env, listing_agent.py, requirements.txt stay as they are.

import hashlib
import html
import streamlit as st
from listing_agent import create_listing_draft, CATEGORIES

st.set_page_config(page_title="AI Listing Assistant", layout="wide")

# --- Look and feel (colors and spacing only; no logic here) ---
st.markdown(
    """
<style>
.block-container {max-width: 1100px; padding-top: 2rem;}
.hero {background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #fff;
    padding: 1.2rem 1.5rem; border-radius: 16px; margin-bottom: 1.2rem;}
.hero h1 {margin: 0; font-size: 1.7rem; color: #fff;}
.hero p {margin: .3rem 0 0 0; opacity: .92;}
.step {font-weight: 700; color: #4f46e5; letter-spacing: .04em;
    font-size: .8rem; text-transform: uppercase; margin-bottom: .2rem;}
.card {border: 1px solid #e5e7eb; border-radius: 16px; padding: 1rem 1.2rem;
    background: #ffffff; color: #111827; box-shadow: 0 2px 10px rgba(0,0,0,.06);}
.card .cat {display: inline-block; background: #eef2ff; color: #4338ca;
            border-radius: 999px; padding: 2px 10px; font-size: .8rem;}
.card h3 {margin: .5rem 0 .3rem 0; color: #111827;}
.card .desc {white-space: pre-wrap; color: #374151; font-size: .95rem;}
.card .price {margin-top: .8rem; padding: .6rem .8rem; background: #fffbeb;
            border: 1px solid #fde68a; border-radius: 10px; color: #78350f;
            font-size: .9rem;}
.card .empty {color: #9ca3af; font-style: italic;}
button[kind="primary"], button[data-testid="stBaseButton-primary"] {
background: #4f46e5; border: none; color: #fff; font-weight: 600; border-radius: 10px;}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {background: #4338ca;}
button[kind="primary"]:disabled, button[data-testid="stBaseButton-primary"]:disabled {background: #c7d2fe;}
.demo {font-size: .8rem; color: #6b7280; margin-top: .6rem;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><h1>AI Listing Assistant</h1>'
    "<p>Upload a photo, add what you know, and get a ready-to-edit listing.</p></div>",
    unsafe_allow_html=True,
)

BLANK_DRAFT = {
    "title": "",
    "description": "",
    "category": "Other",
    "price_range": {"min": None, "max": None, "reason": ""},
}


def build_details(brand_model, ram, storage, age, condition, defects, extra):
    """Join the filled boxes into one text for the AI.
    Empty boxes are left out, so we never send made-up details."""
    lines = []
    if brand_model.strip():
        lines.append("Brand/model: " + brand_model.strip())
    if ram.strip():
        lines.append("RAM: " + ram.strip())
    if storage.strip():
        lines.append("Storage: " + storage.strip())
    if age.strip():
        lines.append("Age: " + age.strip())
    if condition != "Select...":
        lines.append("Condition: " + condition)
    if defects.strip():
        lines.append("Defects/damage: " + defects.strip())
    if extra.strip():
        lines.append("Other details: " + extra.strip())
    if not lines:
        return "Seller gave no extra details. Describe only what the photo shows."
    return "\n".join(lines)


def preview_card(title, desc, cat, price):
    """HTML preview of the listing. All seller/AI text is escaped first."""
    t = html.escape(title.strip()) or '<span class="empty">No title yet</span>'
    d = html.escape(desc.strip()) or '<span class="empty">No description yet</span>'
    if price["min"] is not None and price["max"] is not None:
        p = (f"Suggested price: {html.escape(str(price['min']))} to "
            f"{html.escape(str(price['max']))} INR<br>"
            f"{html.escape(str(price['reason']))}<br>"
            "<b>Only an AI estimate, not a checked market price.</b>")
    else:
        p = "No AI price suggestion. Enter your own price when you publish."
    return (f'<div class="card"><span class="cat">{html.escape(cat)}</span>'
            f"<h3>{t}</h3><div class=\"desc\">{d}</div>"
            f'<div class="price">{p}</div>'
            '<div class="demo">Preview only - nothing is live.</div></div>')


left, right = st.columns([1, 1.15], gap="large")

# --- Left: photo ---
with left:
    st.markdown('<div class="step">Step 1</div>', unsafe_allow_html=True)
    st.subheader("Product photo")
    photo = st.file_uploader("Upload a product photo", type=["jpg", "jpeg", "png"],
                            label_visibility="collapsed")
    if photo is not None:
        st.image(photo.getvalue(), use_container_width=True)
        # Fingerprint of the actual photo bytes. A different photo always clears
        # the old draft, even if the new file has the same name and size.
        photo_id = hashlib.md5(photo.getvalue()).hexdigest()
        if st.session_state.get("photo_id") != photo_id:
            st.session_state["photo_id"] = photo_id
            st.session_state.pop("draft", None)
    else:
        st.info("Your photo preview will appear here.")

# --- Right: details ---
with right:
    st.markdown('<div class="step">Step 2</div>', unsafe_allow_html=True)
    st.subheader("What do you know?")
    st.caption("All optional. Leave a box empty if you do not know it - "
            "empty boxes are not sent to the AI.")
    brand_model = st.text_input("Brand and model", placeholder="Samsung Galaxy M32")
    c1, c2 = st.columns(2)
    ram = c1.text_input("RAM", placeholder="6 GB")
    storage = c2.text_input("Storage", placeholder="128 GB")
    c3, c4 = st.columns(2)
    age = c3.text_input("Age (with unit)", placeholder="2 years or 8 months")
    condition = c4.selectbox(
        "Condition", ["Select...", "New", "Like new", "Good", "Fair", "Needs repair"])
    if age.strip().isdigit():
        st.warning("Age needs a unit - write for example '25 months' or '2 years'. "
                "Without it the AI may guess wrong.")
    defects = st.text_input("Defects or damage", placeholder="Small scratch on the back")
    extra = st.text_area("Anything else",
                        placeholder="Accessories, bill, box, reason for selling...",
                        height=90)
    generate = st.button("Generate listing", type="primary",
                        use_container_width=True, disabled=photo is None)
    if photo is None:
        st.caption("Upload a photo first to turn on this button.")

# --- Generate ---
if photo and generate:
    mime = "image/png" if photo.name.lower().endswith("png") else "image/jpeg"
    details = build_details(brand_model, ram, storage, age, condition, defects, extra)
    with st.spinner("AI is writing your listing..."):
        try:
            st.session_state["draft"] = create_listing_draft(
                photo.getvalue(), details, mime)
        except Exception as e:
            st.error("AI failed. You can still list manually below.")  # FR-7
            st.caption(str(e))
            st.session_state["draft"] = dict(BLANK_DRAFT)
    # Put the new draft into the edit boxes (clears edits from the last draft).
    d = st.session_state["draft"]
    st.session_state["edit_title"] = d["title"]
    st.session_state["edit_desc"] = d["description"]
    st.session_state["edit_cat"] = (
        d["category"] if d["category"] in CATEGORIES else "Other")

# --- Review: edit on the left, live preview on the right ---
if "draft" in st.session_state:
    d = st.session_state["draft"]
    st.divider()
    st.markdown('<div class="step">Step 3</div>', unsafe_allow_html=True)
    st.subheader("Review and edit - nothing goes live until you approve")
    edit_col, view_col = st.columns([1.1, 1], gap="large")
    with edit_col:
        # The keys keep your edits safe when the page reruns.
        title = st.text_input("Title", key="edit_title")
        desc = st.text_area("Description", height=170, key="edit_desc")
        cat = st.selectbox("Category", CATEGORIES, key="edit_cat")
        if st.button("Approve and publish"):                       # FR-5
            st.success("Approved! (In a real app this would save to the database.)")
    with view_col:
        st.caption("Live preview - updates as you edit")
        st.markdown(preview_card(title, desc, cat, d["price_range"]),
                    unsafe_allow_html=True)
