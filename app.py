import streamlit as st
import pandas as pd
import requests
import re
import zipfile
from io import BytesIO
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

st.set_page_config(page_title="Food Intelligence App", layout="wide")
st.title("Food Intelligence App")
st.caption("Predictive database search: Customer database + sample database + USDA + Open Food Facts")

BADGES = {
    "Customer": "CUSTOMER",
    "Sample": "SAMPLE",
    "USDA": "USDA",
    "Open Food Facts": "OFF",
}

DEFAULT_PRODUCTS = [
    {"name":"Chicken Roti-Bulk", "source":"Sample", "calories":37274, "protein":410, "fat":620, "carbs":2800, "salt":42, "allergens":"", "ingredients":"chicken thigh, spices, oil, garlic, onion", "serving_note":"37274 cal per recipe yield"},
    {"name":"Harissa Chicken-Bulk", "source":"Sample", "calories":4372, "protein":360, "fat":190, "carbs":48, "salt":18, "allergens":"", "ingredients":"chicken, harissa paste, oil, garlic, lemon", "serving_note":"4372 cal per recipe yield"},
    {"name":"Hot Honey Harissa Chicken-3oz portion", "source":"Sample", "calories":209, "protein":22, "fat":8, "carbs":10, "salt":0.9, "allergens":"", "ingredients":"chicken, honey, harissa paste, spices", "serving_note":"209 cal per 3 oz portion"},
    {"name":"Chicken Roti Marinade", "source":"Sample", "calories":35665, "protein":12, "fat":3100, "carbs":120, "salt":64, "allergens":"mustard", "ingredients":"oil, lemon juice, garlic, mustard, spices", "serving_note":"35665 cal per recipe yield"},
    {"name":"Chicken, broilers or fryers, thigh, meat only, cooked, roasted", "source":"Sample", "calories":251, "protein":25, "fat":16, "carbs":0, "salt":0.22, "allergens":"", "ingredients":"chicken thigh meat", "serving_note":"251 cal per cup, chopped or diced"},
    {"name":"Pacific Organic Low Sodium Chicken Broth", "source":"Sample", "calories":10, "protein":1, "fat":0, "carbs":1, "salt":0.24, "allergens":"", "ingredients":"chicken broth, chicken flavor, sea salt", "serving_note":"10 cal per 240 ml"},
    {"name":"Wheat Bun", "source":"Sample", "calories":140, "protein":5, "fat":2, "carbs":26, "salt":0.55, "allergens":"cereals containing gluten", "ingredients":"wheat flour, water, yeast, salt", "serving_note":"140 cal per bun"},
    {"name":"Cheddar Cheese", "source":"Sample", "calories":113, "protein":7, "fat":9, "carbs":1, "salt":0.18, "allergens":"milk", "ingredients":"milk, salt, cultures, enzymes", "serving_note":"113 cal per slice"},
]

if "products" not in st.session_state:
    st.session_state.products = DEFAULT_PRODUCTS.copy()
if "recipe_items" not in st.session_state:
    st.session_state.recipe_items = []
if "saved_recipes" not in st.session_state:
    st.session_state.saved_recipes = []


def safe_float(value):
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def normalize_product(product):
    """Ensure every search result has the same keys."""
    return {
        "name": str(product.get("name", "Unnamed item")),
        "source": str(product.get("source", "Unknown")),
        "calories": safe_float(product.get("calories", 0)),
        "protein": safe_float(product.get("protein", 0)),
        "fat": safe_float(product.get("fat", 0)),
        "carbs": safe_float(product.get("carbs", 0)),
        "salt": safe_float(product.get("salt", 0)),
        "allergens": str(product.get("allergens", "") or ""),
        "ingredients": str(product.get("ingredients", "") or ""),
        "serving_note": str(product.get("serving_note", "") or f"{safe_float(product.get('calories', 0))} cal per serving"),
    }


def detect_allergens(text):
    t = (text or "").lower()
    hits = []
    rules = {
        "milk": ["milk", "cheese", "butter", "cream", "whey", "casein"],
        "cereals containing gluten": ["wheat", "barley", "rye", "oats", "spelt", "gluten"],
        "soybeans": ["soy", "soya", "soybean"],
        "eggs": ["egg"],
        "peanuts": ["peanut"],
        "nuts": ["almond", "cashew", "walnut", "pecan", "hazelnut", "pistachio"],
        "sesame": ["sesame"],
        "mustard": ["mustard"],
        "fish": ["fish"],
        "crustaceans": ["shrimp", "prawn", "crab", "lobster"],
        "molluscs": ["clam", "oyster", "mussel", "scallop"],
        "celery": ["celery"],
        "lupin": ["lupin"],
        "sulphites": ["sulfite", "sulphite", "sulfur dioxide", "sulphur dioxide"],
    }
    for allergen, words in rules.items():
        if any(w in t for w in words):
            hits.append(allergen)
    return ", ".join(sorted(set(hits)))



def extract_ingredients_from_text(text):
    raw = text or ""
    lower = raw.lower()
    if "ingredients" not in lower:
        return ""
    start = lower.find("ingredients")
    part = raw[start:]
    part = re.sub(r"^\s*ingredients\s*[:\-]?\s*", "", part.strip(), flags=re.IGNORECASE)
    stops = ["nutrition", "allergen", "contains", "storage", "preparation", "directions", "serving", "specification"]
    low_part = part.lower()
    positions = [low_part.find(stop) for stop in stops if low_part.find(stop) > 0]
    if positions:
        part = part[:min(positions)]
    return " ".join(part.replace("\n", " ").split()).strip(" .:")


def find_nutrient_value(text, labels):
    lower = (text or "").lower()
    for label in labels:
        pattern = rf"{re.escape(label.lower())}\D*(\d+(?:\.\d+)?)"
        match = re.search(pattern, lower)
        if match:
            return safe_float(match.group(1))
    return 0.0


def parse_product_spec_text(text, filename="Uploaded Spec"):
    raw = text or ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    guessed_name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip().title()
    for line in lines[:8]:
        low = line.lower()
        if any(token in low for token in ["product name", "item name", "description"]):
            if ":" in line:
                guessed_name = line.split(":", 1)[1].strip() or guessed_name
                break
        elif len(line) <= 80 and not any(token in low for token in ["ingredients", "nutrition", "allergen", "contains"]):
            guessed_name = line
            break

    ingredients = extract_ingredients_from_text(raw)
    allergens = detect_allergens(raw + " " + ingredients)
    sodium_mg = find_nutrient_value(raw, ["sodium"])
    salt_g = find_nutrient_value(raw, ["salt"])
    if salt_g == 0 and sodium_mg:
        salt_g = round(sodium_mg * 2.5 / 1000, 3)
    calories = find_nutrient_value(raw, ["calories", "kcal", "energy"])
    product = normalize_product({
        "name": guessed_name,
        "source": "Customer",
        "calories": calories,
        "protein": find_nutrient_value(raw, ["protein"]),
        "fat": find_nutrient_value(raw, ["total fat", "fat"]),
        "carbs": find_nutrient_value(raw, ["total carbohydrate", "carbohydrate", "carbs"]),
        "salt": salt_g,
        "allergens": allergens,
        "ingredients": ingredients,
        "serving_note": f"{calories:g} cal per extracted serving" if calories else "Extracted from uploaded specification",
    })
    product["filename"] = filename
    product["raw_text"] = raw
    return product


def extract_text_from_pdf_bytes(file_bytes):
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def extract_text_from_file_bytes(name, data):
    lower = name.lower()
    if lower.endswith(".txt"):
        try:
            return data.decode("utf-8")
        except Exception:
            return data.decode("latin-1", errors="ignore")
    if lower.endswith(".pdf"):
        return extract_text_from_pdf_bytes(data)
    return ""


def parse_batch_uploads(uploaded_files):
    parsed = []
    errors = []
    for uploaded in uploaded_files:
        name = uploaded.name
        data = uploaded.read()
        lower = name.lower()
        if lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        fname = info.filename
                        fl = fname.lower()
                        if not (fl.endswith(".txt") or fl.endswith(".pdf")):
                            continue
                        inner = zf.read(info)
                        extracted = extract_text_from_file_bytes(fname, inner)
                        if extracted.strip():
                            parsed.append(parse_product_spec_text(extracted, fname))
                        else:
                            errors.append(f"No text extracted from {fname}")
            except Exception as e:
                errors.append(f"Could not read ZIP {name}: {e}")
        elif lower.endswith(".txt") or lower.endswith(".pdf"):
            extracted = extract_text_from_file_bytes(name, data)
            if extracted.strip():
                parsed.append(parse_product_spec_text(extracted, name))
            else:
                errors.append(f"No text extracted from {name}")
        else:
            errors.append(f"Unsupported file type: {name}")
    return parsed, errors


def totals(items):
    t = {"calories":0.0,"protein":0.0,"fat":0.0,"carbs":0.0,"salt":0.0}
    allergens = set()
    ingredients = []
    for item in items:
        qty = float(item.get("qty", 1))
        for k in t:
            t[k] += float(item.get(k, 0)) * qty
        if item.get("allergens"):
            for a in str(item["allergens"]).split(","):
                if a.strip():
                    allergens.add(a.strip())
        if item.get("ingredients"):
            ingredients.append(str(item["ingredients"]))
    return t, sorted(allergens), ", ".join(ingredients)


def prediction_score(product, query):
    if not query:
        return 0
    q = query.lower().strip()
    name = product.get("name", "").lower()
    ingredients = product.get("ingredients", "").lower()
    source = product.get("source", "").lower()
    allergens = product.get("allergens", "").lower()
    haystack = f"{name} {ingredients} {source} {allergens}"
    if name.startswith(q):
        return 100
    if q in name:
        return 80
    if any(word.startswith(q) for word in name.split()):
        return 70
    if q in ingredients:
        return 55
    if q in haystack:
        return 40
    words = [w for w in q.split() if w]
    if words and all(w in haystack for w in words):
        return 35
    return 0


def search_customer_and_sample(query):
    scored = []
    for p in st.session_state.products:
        p = normalize_product(p)
        if not query:
            scored.append((1, p))
        else:
            score = prediction_score(p, query)
            if score > 0:
                scored.append((score, p))
    scored.sort(key=lambda x: (x[0], x[1].get("calories", 0)), reverse=True)
    return [p for _, p in scored]


@st.cache_data(ttl=3600, show_spinner=False)
def search_open_food_facts(query, limit=15):
    if not query or len(query.strip()) < 3:
        return []
    try:
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": limit,
            "fields": "product_name,generic_name,brands,ingredients_text,nutriments,allergens_tags"
        }
        data = requests.get(url, params=params, timeout=8).json()
        results = []
        for item in data.get("products", []):
            name = item.get("product_name") or item.get("generic_name") or "Open Food Facts item"
            nutriments = item.get("nutriments", {}) or {}
            ingredients = item.get("ingredients_text", "") or ""
            calories = safe_float(nutriments.get("energy-kcal_100g"))
            fat = safe_float(nutriments.get("fat_100g"))
            carbs = safe_float(nutriments.get("carbohydrates_100g"))
            protein = safe_float(nutriments.get("proteins_100g"))
            salt = safe_float(nutriments.get("salt_100g"))
            allergens = detect_allergens(ingredients + " " + " ".join(item.get("allergens_tags", [])))
            results.append(normalize_product({
                "name": name,
                "source": "Open Food Facts",
                "calories": calories,
                "protein": protein,
                "fat": fat,
                "carbs": carbs,
                "salt": salt,
                "allergens": allergens,
                "ingredients": ingredients,
                "serving_note": f"{calories:g} cal per 100 g" if calories else "Nutrition per 100 g when available",
            }))
        return results
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def search_usda(query, api_key, limit=15):
    if not api_key or not query or len(query.strip()) < 3:
        return []
    try:
        url = "https://api.nal.usda.gov/fdc/v1/foods/search"
        params = {"query": query, "pageSize": limit, "api_key": api_key}
        data = requests.get(url, params=params, timeout=8).json()
        results = []
        for food in data.get("foods", []):
            n = {"calories": 0, "protein": 0, "fat": 0, "carbs": 0, "salt": 0}
            for nutrient in food.get("foodNutrients", []):
                name = (nutrient.get("nutrientName") or "").lower()
                unit = (nutrient.get("unitName") or "").lower()
                value = safe_float(nutrient.get("value"))
                if "energy" in name and ("kcal" in unit or unit == "kcal"):
                    n["calories"] = value
                elif name == "protein":
                    n["protein"] = value
                elif name in ["total lipid (fat)", "total fat"]:
                    n["fat"] = value
                elif "carbohydrate" in name:
                    n["carbs"] = value
                elif name == "sodium, na":
                    n["salt"] = round(value * 2.5 / 1000, 3)
            desc = food.get("description", "USDA food").title()
            results.append(normalize_product({
                "name": desc,
                "source": "USDA",
                "calories": n["calories"],
                "protein": n["protein"],
                "fat": n["fat"],
                "carbs": n["carbs"],
                "salt": n["salt"],
                "allergens": detect_allergens(desc),
                "ingredients": desc.lower(),
                "serving_note": f"{n['calories']:g} cal per 100 g" if n["calories"] else "USDA nutrition per listed measure",
            }))
        return results
    except Exception:
        return []


def combined_database_search(query):
    api_key = st.secrets.get("USDA_API_KEY", "")
    local = search_customer_and_sample(query)
    usda = search_usda(query, api_key, limit=15) if len(query.strip()) >= 3 else []
    off = search_open_food_facts(query, limit=15) if len(query.strip()) >= 3 else []

    # Keep local matches first, then USDA, then OFF. Remove exact duplicate names from same source.
    seen = set()
    merged = []
    for item in local + usda + off:
        key = (item.get("source", ""), item.get("name", "").lower())
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged, {"Customer/Sample": len(local), "USDA": len(usda), "Open Food Facts": len(off)}


def product_table(products):
    return pd.DataFrame([normalize_product(p) for p in products])


def badge_html(source):
    label = BADGES.get(source, source.upper() if source else "SOURCE")
    return f"<span style='font-size:11px; padding:2px 7px; border:1px solid #d8d2a8; border-radius:8px; background:#fbf7df; color:#776b22; font-weight:700;'>{label}</span>"


def render_search_result(product, index, prefix="search"):
    product = normalize_product(product)
    with st.container(border=True):
        icon_col, text_col, action_col, preview_col = st.columns([0.4, 5.7, 1.5, 1.2])
        with icon_col:
            if product.get("source") == "Customer":
                st.markdown("👤")
            elif product.get("source") == "USDA":
                st.markdown("✅")
            elif product.get("source") == "Open Food Facts":
                st.markdown("👥")
            else:
                st.markdown("🍽️")
        with text_col:
            st.markdown(f"**{product['name']}** &nbsp; {badge_html(product.get('source', 'Customer'))}", unsafe_allow_html=True)
            st.caption(product.get("serving_note") or f"{product.get('calories', 0):g} cal per serving")
            if product.get("allergens"):
                st.warning(f"Allergens: {product.get('allergens')}")
        with action_col:
            if st.button("+ Add to Recipe", key=f"{prefix}_add_{index}_{product['source']}_{product['name']}"):
                item = dict(product)
                item["qty"] = 1.0
                st.session_state.recipe_items.append(item)
                st.success(f"Added {product['name']}")
        with preview_col:
            with st.expander("Preview"):
                st.write("**Ingredients**")
                st.write(product.get("ingredients", "") or "Not available")
                st.write("**Allergens**")
                st.write(product.get("allergens", "") or "none detected")
                st.write("**Nutrition**")
                st.json({
                    "calories": product.get("calories", 0),
                    "protein_g": product.get("protein", 0),
                    "fat_g": product.get("fat", 0),
                    "carbs_g": product.get("carbs", 0),
                    "salt_g": product.get("salt", 0),
                })


tabs = st.tabs(["Dashboard", "Add Product", "Batch Upload", "Recipe Builder", "Saved Recipes"])

with tabs[0]:
    st.header("Dashboard")
    c1, c2, c3 = st.columns(3)
    c1.metric("Products", len(st.session_state.products))
    c2.metric("Recipe Items", len(st.session_state.recipe_items))
    c3.metric("Saved Recipes", len(st.session_state.saved_recipes))
    st.subheader("Customer + Sample Database")
    st.dataframe(product_table(st.session_state.products), use_container_width=True)
    st.info("USDA results require a Streamlit secret named USDA_API_KEY. Open Food Facts does not require a key.")

with tabs[1]:
    st.header("Add Customer Product / Ingredient")
    name = st.text_input("Product name")
    ingredients = st.text_area("Ingredients")
    allergens = st.text_input("Allergens", placeholder="milk, cereals containing gluten")
    c1, c2, c3, c4, c5 = st.columns(5)
    calories = c1.number_input("Calories", min_value=0.0, value=0.0)
    protein = c2.number_input("Protein g", min_value=0.0, value=0.0)
    fat = c3.number_input("Fat g", min_value=0.0, value=0.0)
    carbs = c4.number_input("Carbs g", min_value=0.0, value=0.0)
    salt = c5.number_input("Salt g", min_value=0.0, value=0.0)
    serving_note = st.text_input("Serving note", placeholder="Example: 150 cal per 100 g")
    if st.button("Save Product"):
        if name:
            st.session_state.products.append(normalize_product({
                "name": name,
                "source": "Customer",
                "calories": calories,
                "protein": protein,
                "fat": fat,
                "carbs": carbs,
                "salt": salt,
                "allergens": allergens or detect_allergens(ingredients),
                "ingredients": ingredients,
                "serving_note": serving_note or f"{calories:g} cal per serving",
            }))
            st.success("Saved")
        else:
            st.warning("Add a name first")

with tabs[2]:
    st.header("Batch Upload Product Specifications")
    st.caption("Upload multiple .txt/.pdf files or a .zip folder containing individual specification files. Each file becomes one searchable product/ingredient.")

    uploads = st.file_uploader(
        "Upload product specification files",
        type=["txt", "pdf", "zip"],
        accept_multiple_files=True,
    )

    if uploads:
        if st.button("Extract Products from Uploaded Files"):
            parsed, errors = parse_batch_uploads(uploads)
            st.session_state["batch_preview"] = parsed
            st.session_state["batch_errors"] = errors

    batch_preview = st.session_state.get("batch_preview", [])
    batch_errors = st.session_state.get("batch_errors", [])

    if batch_errors:
        st.warning("Some files need review:")
        for err in batch_errors:
            st.write("-", err)

    if batch_preview:
        st.success(f"Extracted {len(batch_preview)} product(s). Review below, then add them to the database.")
        st.dataframe(product_table(batch_preview), use_container_width=True)

        for i, product in enumerate(batch_preview):
            with st.expander(f"Review: {product['name']}"):
                st.write("Source file:", product.get("filename", ""))
                product["name"] = st.text_input("Product name", value=product["name"], key=f"batch_name_{i}")
                product["ingredients"] = st.text_area("Ingredients", value=product.get("ingredients", ""), key=f"batch_ing_{i}", height=90)
                product["allergens"] = st.text_input("Allergens", value=product.get("allergens", ""), key=f"batch_allergens_{i}")
                c1, c2, c3, c4, c5 = st.columns(5)
                product["calories"] = c1.number_input("Calories", value=float(product.get("calories", 0)), key=f"batch_cal_{i}")
                product["protein"] = c2.number_input("Protein g", value=float(product.get("protein", 0)), key=f"batch_pro_{i}")
                product["fat"] = c3.number_input("Fat g", value=float(product.get("fat", 0)), key=f"batch_fat_{i}")
                product["carbs"] = c4.number_input("Carbs g", value=float(product.get("carbs", 0)), key=f"batch_carb_{i}")
                product["salt"] = c5.number_input("Salt g", value=float(product.get("salt", 0)), key=f"batch_salt_{i}")

        if st.button("Add All Extracted Products to Database"):
            for product in batch_preview:
                product["source"] = "Customer"
                st.session_state.products.append(normalize_product(product))
            st.success(f"Added {len(batch_preview)} products to database search.")
            st.session_state["batch_preview"] = []
            st.session_state["batch_errors"] = []
            st.rerun()
    else:
        st.info("Tip: ZIP upload is the easiest way to upload a folder of product specs from your computer.")

with tabs[3]:
    st.header("Recipe Builder")
    st.subheader("Database Search")
    st.caption("Start typing to preview predicted matches from Customer/Sample, USDA, and Open Food Facts. No search button needed.")
    q = st.text_input("Search ingredients/products", placeholder="Type chicken, bun, cheese, flour...", label_visibility="collapsed")

    if q.strip() and len(q.strip()) < 3:
        st.caption("Type at least 3 characters to search external databases. Customer/sample predictions may appear sooner.")

    with st.spinner("Searching databases...") if len(q.strip()) >= 3 else st.spinner("Loading suggestions..."):
        results, source_counts = combined_database_search(q)

    st.caption(f"Results by source: Customer/Sample {source_counts['Customer/Sample']} | USDA {source_counts['USDA']} | Open Food Facts {source_counts['Open Food Facts']}")

    if q and not results:
        st.info("No matching products found. Add it in the Add Product tab.")
    else:
        if q:
            st.caption(f"Showing predicted matches for: {q}")
        else:
            st.caption("Suggested database items")
        for i, p in enumerate(results[:24]):
            render_search_result(p, i, prefix="predictive")

    st.divider()
    st.subheader("Current Recipe Items")
    if not st.session_state.recipe_items:
        st.info("Use Database Search above to add items to your recipe.")
    else:
        for idx, item in enumerate(st.session_state.recipe_items):
            c1, c2, c3 = st.columns([5, 2, 1])
            c1.write(item["name"])
            st.session_state.recipe_items[idx]["qty"] = c2.number_input("Qty", min_value=0.0, value=float(item.get("qty", 1)), step=0.25, key=f"qty_{idx}")
            if c3.button("Remove", key=f"rem_{idx}"):
                st.session_state.recipe_items.pop(idx)
                st.rerun()

        recipe_name = st.text_input("Recipe name")
        servings = st.number_input("Servings", min_value=1, value=1)
        total, allergens, ingredient_list = totals(st.session_state.recipe_items)
        per = {k: round(v / servings, 2) for k, v in total.items()}

        st.subheader("Nutrition per serving")
        st.json(per)
        st.subheader("Ingredient statement")
        st.text_area("Ingredient list", ingredient_list, height=100)
        st.subheader("Allergen declaration")
        allergen_text = "Contains: " + (", ".join(allergens) if allergens else "No declarable allergens detected")
        st.text_area("Allergens", allergen_text, height=80)
        st.subheader("UK-style label draft")
        label = f"""{recipe_name or 'Recipe'}\n\nIngredients: {ingredient_list}\n\n{allergen_text}\n\nNutrition per serving:\nEnergy: {per['calories']} kcal\nFat: {per['fat']} g\nCarbohydrate: {per['carbs']} g\nProtein: {per['protein']} g\nSalt: {per['salt']} g\n"""
        st.text_area("Label preview", label, height=260)

        if st.button("Save Recipe"):
            if recipe_name:
                st.session_state.saved_recipes.append({"name": recipe_name, "servings": servings, "items": list(st.session_state.recipe_items), "label": label, "nutrition_per_serving": per})
                st.success("Recipe saved")
            else:
                st.warning("Add a recipe name")

with tabs[4]:
    st.header("Saved Recipes")
    if not st.session_state.saved_recipes:
        st.info("No saved recipes yet")
    else:
        for r in st.session_state.saved_recipes:
            with st.expander(r["name"]):
                st.text_area("Label", r["label"], height=220)
                st.download_button("Download label text", r["label"], file_name=f"{r['name']}_label.txt")
