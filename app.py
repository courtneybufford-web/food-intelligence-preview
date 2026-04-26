import io
import re
from datetime import datetime

import pandas as pd
import streamlit as st

try:
    import requests
except Exception:  # keeps preview running if requests is not available
    requests = None

st.set_page_config(page_title="Food Intelligence Platform", layout="wide")

st.title("Food Intelligence Platform — MVP Preview")
st.caption(
    "Upload or paste product specs, extract ingredients/allergens/nutrients, search products, "
    "build recipes, scale by servings, export spreadsheets, and generate nutrition panel previews."
)

# -----------------------------
# Session state
# -----------------------------
if "products" not in st.session_state:
    st.session_state.products = []

if "recipes" not in st.session_state:
    st.session_state.recipes = []

if "usda_results" not in st.session_state:
    st.session_state.usda_results = []

# -----------------------------
# Nutrient definitions
# -----------------------------
NUTRIENT_DEFINITIONS = {
    "calories": ("Calories", "kcal"),
    "total_fat_g": ("Total Fat", "g"),
    "saturated_fat_g": ("Saturated Fat", "g"),
    "trans_fat_g": ("Trans Fat", "g"),
    "polyunsaturated_fat_g": ("Polyunsaturated Fat", "g"),
    "monounsaturated_fat_g": ("Monounsaturated Fat", "g"),
    "cholesterol_mg": ("Cholesterol", "mg"),
    "sodium_mg": ("Sodium", "mg"),
    "total_carbs_g": ("Total Carbohydrate", "g"),
    "dietary_fiber_g": ("Dietary Fiber", "g"),
    "soluble_fiber_g": ("Soluble Fiber", "g"),
    "insoluble_fiber_g": ("Insoluble Fiber", "g"),
    "total_sugars_g": ("Total Sugars", "g"),
    "added_sugars_g": ("Added Sugars", "g"),
    "protein_g": ("Protein", "g"),
    "vitamin_d_mcg": ("Vitamin D", "mcg"),
    "calcium_mg": ("Calcium", "mg"),
    "iron_mg": ("Iron", "mg"),
    "potassium_mg": ("Potassium", "mg"),
    "vitamin_a_mcg": ("Vitamin A", "mcg"),
    "vitamin_c_mg": ("Vitamin C", "mg"),
    "vitamin_e_mg": ("Vitamin E", "mg"),
    "vitamin_k_mcg": ("Vitamin K", "mcg"),
    "thiamin_mg": ("Thiamin", "mg"),
    "riboflavin_mg": ("Riboflavin", "mg"),
    "niacin_mg": ("Niacin", "mg"),
    "vitamin_b6_mg": ("Vitamin B6", "mg"),
    "folate_mcg": ("Folate", "mcg"),
    "vitamin_b12_mcg": ("Vitamin B12", "mcg"),
    "biotin_mcg": ("Biotin", "mcg"),
    "pantothenic_acid_mg": ("Pantothenic Acid", "mg"),
    "phosphorus_mg": ("Phosphorus", "mg"),
    "iodine_mcg": ("Iodine", "mcg"),
    "magnesium_mg": ("Magnesium", "mg"),
    "zinc_mg": ("Zinc", "mg"),
    "selenium_mcg": ("Selenium", "mcg"),
    "copper_mg": ("Copper", "mg"),
    "manganese_mg": ("Manganese", "mg"),
    "chromium_mcg": ("Chromium", "mcg"),
    "molybdenum_mcg": ("Molybdenum", "mcg"),
    "chloride_mg": ("Chloride", "mg"),
    "choline_mg": ("Choline", "mg"),
}

NUTRIENT_FIELDS = list(NUTRIENT_DEFINITIONS.keys())

RECIPE_TOTAL_FIELDS = [
    "calories",
    "total_fat_g",
    "saturated_fat_g",
    "trans_fat_g",
    "cholesterol_mg",
    "sodium_mg",
    "total_carbs_g",
    "dietary_fiber_g",
    "total_sugars_g",
    "added_sugars_g",
    "protein_g",
    "vitamin_d_mcg",
    "calcium_mg",
    "iron_mg",
    "potassium_mg",
]

# Approximate adult daily values for preview calculations only.
US_DV = {
    "total_fat_g": 78,
    "saturated_fat_g": 20,
    "cholesterol_mg": 300,
    "sodium_mg": 2300,
    "total_carbs_g": 275,
    "dietary_fiber_g": 28,
    "added_sugars_g": 50,
    "protein_g": 50,
    "vitamin_d_mcg": 20,
    "calcium_mg": 1300,
    "iron_mg": 18,
    "potassium_mg": 4700,
}

CANADA_DV = {
    "total_fat_g": 75,
    "saturated_fat_g": 20,
    "cholesterol_mg": 300,
    "sodium_mg": 2300,
    "total_carbs_g": 275,
    "dietary_fiber_g": 28,
    "total_sugars_g": 100,
    "protein_g": 50,
    "vitamin_d_mcg": 20,
    "calcium_mg": 1300,
    "iron_mg": 18,
    "potassium_mg": 4700,
}

# UK labels typically emphasize per 100g/ml and per serving rather than %DV in the same way.
UK_CORE_FIELDS = [
    "calories",
    "total_fat_g",
    "saturated_fat_g",
    "total_carbs_g",
    "total_sugars_g",
    "protein_g",
    "sodium_mg",
]

# -----------------------------
# Utilities
# -----------------------------
def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def to_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def fmt(value, decimals=1):
    if value is None:
        return "—"
    try:
        value = float(value)
    except Exception:
        return str(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def nutrition_value(item, field):
    value = item.get("nutrition", {}).get(field)
    return value if value is not None else 0


def pct_dv(nutrition, field, dv_map):
    value = nutrition.get(field)
    dv = dv_map.get(field)
    if value is None or not dv:
        return None
    return round((value / dv) * 100)


def scale_nutrition(nutrition, factor):
    scaled = {}
    for key in NUTRIENT_FIELDS:
        value = nutrition.get(key)
        scaled[key] = round(value * factor, 3) if value is not None else None
    return scaled


def salt_from_sodium_mg(sodium_mg):
    if sodium_mg is None:
        return None
    # Salt equivalent = sodium x 2.5. Convert mg sodium to g salt.
    return round((sodium_mg * 2.5) / 1000, 3)


def extract_text_from_upload(uploaded_file):
    if uploaded_file is None:
        return ""

    if uploaded_file.type == "text/plain":
        return uploaded_file.read().decode("utf-8", errors="ignore")

    if uploaded_file.type == "application/pdf":
        return (
            "PDF uploaded. In this free preview, paste the PDF text below. "
            "The backend version can add real PDF extraction with PyMuPDF/pdfplumber/OCR."
        )

    return ""

# -----------------------------
# Nutrition extraction
# -----------------------------
def parse_nutrients(text):
    lower = text.lower()

    nutrient_patterns = {
        "calories": r"\bcalories\b\D*(\d+(?:\.\d+)?)",
        "total_fat_g": r"\btotal\s+fat\b\D*(\d+(?:\.\d+)?)\s*g?",
        "saturated_fat_g": r"\bsaturated\s+fat\b\D*(\d+(?:\.\d+)?)\s*g?",
        "trans_fat_g": r"\btrans\s+fat\b\D*(\d+(?:\.\d+)?)\s*g?",
        "polyunsaturated_fat_g": r"\bpolyunsaturated\s+fat\b\D*(\d+(?:\.\d+)?)\s*g?",
        "monounsaturated_fat_g": r"\bmonounsaturated\s+fat\b\D*(\d+(?:\.\d+)?)\s*g?",
        "cholesterol_mg": r"\bcholesterol\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "sodium_mg": r"\bsodium\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "total_carbs_g": r"\b(?:total\s+carbohydrate|carbohydrate|carbs)\b\D*(\d+(?:\.\d+)?)\s*g?",
        "dietary_fiber_g": r"\b(?:dietary\s+fiber|fiber)\b\D*(\d+(?:\.\d+)?)\s*g?",
        "soluble_fiber_g": r"\bsoluble\s+fiber\b\D*(\d+(?:\.\d+)?)\s*g?",
        "insoluble_fiber_g": r"\binsoluble\s+fiber\b\D*(\d+(?:\.\d+)?)\s*g?",
        "total_sugars_g": r"\b(?:total\s+sugars|sugars)\b\D*(\d+(?:\.\d+)?)\s*g?",
        "added_sugars_g": r"\badded\s+sugars\b\D*(\d+(?:\.\d+)?)\s*g?",
        "protein_g": r"\bprotein\b\D*(\d+(?:\.\d+)?)\s*g?",
        "vitamin_d_mcg": r"\bvitamin\s+d\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "calcium_mg": r"\bcalcium\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "iron_mg": r"\biron\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "potassium_mg": r"\bpotassium\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "vitamin_a_mcg": r"\bvitamin\s+a\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "vitamin_c_mg": r"\bvitamin\s+c\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "vitamin_e_mg": r"\bvitamin\s+e\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "vitamin_k_mcg": r"\bvitamin\s+k\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "thiamin_mg": r"\b(?:thiamin|vitamin\s+b1)\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "riboflavin_mg": r"\b(?:riboflavin|vitamin\s+b2)\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "niacin_mg": r"\b(?:niacin|vitamin\s+b3)\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "vitamin_b6_mg": r"\bvitamin\s+b6\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "folate_mcg": r"\b(?:folate|folic\s+acid)\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "vitamin_b12_mcg": r"\bvitamin\s+b12\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "biotin_mcg": r"\bbiotin\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "pantothenic_acid_mg": r"\bpantothenic\s+acid\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "phosphorus_mg": r"\bphosphorus\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "iodine_mcg": r"\biodine\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "magnesium_mg": r"\bmagnesium\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "zinc_mg": r"\bzinc\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "selenium_mcg": r"\bselenium\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "copper_mg": r"\bcopper\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "manganese_mg": r"\bmanganese\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "chromium_mcg": r"\bchromium\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "molybdenum_mcg": r"\bmolybdenum\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "chloride_mg": r"\bchloride\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "choline_mg": r"\bcholine\b\D*(\d+(?:\.\d+)?)\s*mg?",
    }

    nutrients = {}
    for key, pattern in nutrient_patterns.items():
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        nutrients[key] = to_float(match.group(1)) if match else None
    return nutrients

# -----------------------------
# Product parsing
# -----------------------------
def parse_ingredients(text):
    lower = text.lower()
    if "ingredients" not in lower:
        return []

    part = lower.split("ingredients", 1)[1]
    stop_words = [
        "nutrition",
        "contains",
        "allergens",
        "allergen",
        "may contain",
        "distributed by",
        "manufactured by",
    ]

    for stop in stop_words:
        if stop in part:
            part = part.split(stop, 1)[0]

    return [i.strip(" :.;\n\t") for i in re.split(r"[,;]", part) if i.strip(" :.;\n\t")]


def parse_allergens(text):
    lower = text.lower()
    allergen_rules = {
        "wheat": "gluten",
        "gluten": "gluten",
        "barley": "gluten",
        "rye": "gluten",
        "milk": "dairy",
        "cheese": "dairy",
        "butter": "dairy",
        "cream": "dairy",
        "whey": "dairy",
        "casein": "dairy",
        "soy": "soy",
        "soybean": "soy",
        "egg": "egg",
        "peanut": "peanut",
        "almond": "tree nuts",
        "cashew": "tree nuts",
        "walnut": "tree nuts",
        "pecan": "tree nuts",
        "hazelnut": "tree nuts",
        "pistachio": "tree nuts",
        "fish": "fish",
        "anchovy": "fish",
        "salmon": "fish",
        "tuna": "fish",
        "shellfish": "shellfish",
        "shrimp": "shellfish",
        "crab": "shellfish",
        "lobster": "shellfish",
        "sesame": "sesame",
    }
    return sorted({allergen for word, allergen in allergen_rules.items() if re.search(rf"\b{re.escape(word)}\b", lower)})


def confidence_score(product):
    score = 0
    if product["ingredients"]:
        score += 35
    if product["allergens"]:
        score += 10
    detected_nutrients = sum(1 for v in product["nutrition"].values() if v is not None)
    score += min(55, detected_nutrients * 4)
    return min(100, score)


def parse_product(text, name, supplier):
    product = {
        "id": f"P{len(st.session_state.products) + 1:04d}",
        "name": name.strip(),
        "supplier": supplier.strip(),
        "ingredients": parse_ingredients(text),
        "allergens": parse_allergens(text),
        "nutrition": parse_nutrients(text),
        "raw_text": text,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    product["confidence"] = confidence_score(product)
    return product

# -----------------------------
# Dataframe/export helpers
# -----------------------------
def products_dataframe(products):
    rows = []
    for p in products:
        row = {
            "ID": p.get("id", ""),
            "Name": p["name"],
            "Supplier": p["supplier"],
            "Confidence": p.get("confidence", 0),
            "Ingredients": ", ".join(p["ingredients"]),
            "Allergens": ", ".join(p["allergens"]) if p["allergens"] else "None",
        }
        for field in ["calories", "protein_g", "total_fat_g", "total_carbs_g", "sodium_mg", "calcium_mg", "iron_mg", "potassium_mg"]:
            row[field] = p["nutrition"].get(field)
        rows.append(row)
    return pd.DataFrame(rows)


def detailed_nutrition_dataframe(nutrition):
    return pd.DataFrame([
        {"Nutrient Key": key, "Nutrient": NUTRIENT_DEFINITIONS[key][0], "Value": nutrition.get(key), "Unit": NUTRIENT_DEFINITIONS[key][1]}
        for key in NUTRIENT_FIELDS
    ])


def full_products_dataframe(products):
    rows = []
    for p in products:
        row = {
            "id": p.get("id", ""),
            "name": p["name"],
            "supplier": p["supplier"],
            "ingredients": ", ".join(p["ingredients"]),
            "allergens": ", ".join(p["allergens"]),
            "confidence": p.get("confidence", 0),
            "created_at": p.get("created_at", ""),
        }
        row.update(p["nutrition"])
        rows.append(row)
    return pd.DataFrame(rows)


def recipes_dataframe(recipes):
    rows = []
    for recipe in recipes:
        row = {
            "name": recipe.get("name"),
            "servings": recipe.get("servings"),
            "portion_description": recipe.get("portion_description"),
            "allergens": ", ".join(recipe.get("allergens", [])),
            "created_at": recipe.get("created_at", ""),
        }
        row.update({f"batch_{k}": v for k, v in recipe.get("nutrition_totals", {}).items()})
        row.update({f"per_serving_{k}": v for k, v in recipe.get("nutrition_per_serving", {}).items()})
        rows.append(row)
    return pd.DataFrame(rows)


def compliance_export_dataframe(source_name, nutrition, region):
    if region == "US":
        fields = ["calories", "total_fat_g", "saturated_fat_g", "trans_fat_g", "cholesterol_mg", "sodium_mg", "total_carbs_g", "dietary_fiber_g", "total_sugars_g", "added_sugars_g", "protein_g", "vitamin_d_mcg", "calcium_mg", "iron_mg", "potassium_mg"]
        dv_map = US_DV
    elif region == "Canada":
        fields = ["calories", "total_fat_g", "saturated_fat_g", "trans_fat_g", "cholesterol_mg", "sodium_mg", "total_carbs_g", "dietary_fiber_g", "total_sugars_g", "protein_g", "potassium_mg", "calcium_mg", "iron_mg"]
        dv_map = CANADA_DV
    else:
        fields = UK_CORE_FIELDS
        dv_map = {}

    rows = []
    for field in fields:
        label, unit = NUTRIENT_DEFINITIONS[field]
        value = nutrition.get(field)
        if region == "UK" and field == "sodium_mg":
            rows.append({"Source": source_name, "Region": region, "Nutrient": "Salt", "Value": salt_from_sodium_mg(value), "Unit": "g", "%DV / RI": None})
        else:
            rows.append({"Source": source_name, "Region": region, "Nutrient": label, "Value": value, "Unit": unit, "%DV / RI": pct_dv(nutrition, field, dv_map)})
    return pd.DataFrame(rows)


def make_excel_export(products, recipes, region="US"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        full_products_dataframe(products).to_excel(writer, sheet_name="Products_Full_Nutrition", index=False)
        products_dataframe(products).to_excel(writer, sheet_name="Products_Summary", index=False)
        if recipes:
            recipes_dataframe(recipes).to_excel(writer, sheet_name="Recipes", index=False)
        compliance_frames = []
        for p in products:
            compliance_frames.append(compliance_export_dataframe(p["name"], p["nutrition"], region))
        for r in recipes:
            compliance_frames.append(compliance_export_dataframe(r["name"], r.get("nutrition_per_serving", {}), region))
        if compliance_frames:
            pd.concat(compliance_frames, ignore_index=True).to_excel(writer, sheet_name=f"{region}_Label_Review", index=False)
    output.seek(0)
    return output.getvalue()

# -----------------------------
# Nutrition label generators
# -----------------------------
def us_nutrition_panel(name, nutrition, serving_size="1 serving"):
    lines = [
        "NUTRITION FACTS — US PREVIEW",
        f"{name}",
        f"Serving size {serving_size}",
        "--------------------------------",
        f"Calories {fmt(nutrition.get('calories'), 0)}",
        "--------------------------------",
        f"Total Fat {fmt(nutrition.get('total_fat_g'))}g   {fmt(pct_dv(nutrition, 'total_fat_g', US_DV), 0)}% DV",
        f"  Saturated Fat {fmt(nutrition.get('saturated_fat_g'))}g   {fmt(pct_dv(nutrition, 'saturated_fat_g', US_DV), 0)}% DV",
        f"  Trans Fat {fmt(nutrition.get('trans_fat_g'))}g",
        f"Cholesterol {fmt(nutrition.get('cholesterol_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'cholesterol_mg', US_DV), 0)}% DV",
        f"Sodium {fmt(nutrition.get('sodium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'sodium_mg', US_DV), 0)}% DV",
        f"Total Carbohydrate {fmt(nutrition.get('total_carbs_g'))}g   {fmt(pct_dv(nutrition, 'total_carbs_g', US_DV), 0)}% DV",
        f"  Dietary Fiber {fmt(nutrition.get('dietary_fiber_g'))}g   {fmt(pct_dv(nutrition, 'dietary_fiber_g', US_DV), 0)}% DV",
        f"  Total Sugars {fmt(nutrition.get('total_sugars_g'))}g",
        f"    Includes {fmt(nutrition.get('added_sugars_g'))}g Added Sugars   {fmt(pct_dv(nutrition, 'added_sugars_g', US_DV), 0)}% DV",
        f"Protein {fmt(nutrition.get('protein_g'))}g",
        "--------------------------------",
        f"Vitamin D {fmt(nutrition.get('vitamin_d_mcg'))}mcg   {fmt(pct_dv(nutrition, 'vitamin_d_mcg', US_DV), 0)}% DV",
        f"Calcium {fmt(nutrition.get('calcium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'calcium_mg', US_DV), 0)}% DV",
        f"Iron {fmt(nutrition.get('iron_mg'))}mg   {fmt(pct_dv(nutrition, 'iron_mg', US_DV), 0)}% DV",
        f"Potassium {fmt(nutrition.get('potassium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'potassium_mg', US_DV), 0)}% DV",
        "",
        "Preview only — not a legal/compliance approval. Confirm rounding, serving size, and label rules before commercial use.",
    ]
    return "\n".join(lines)


def canada_nutrition_panel(name, nutrition, serving_size="1 serving"):
    lines = [
        "NUTRITION FACTS / VALEUR NUTRITIVE — CANADA PREVIEW",
        f"{name}",
        f"Serving size / Portion {serving_size}",
        "--------------------------------",
        f"Calories {fmt(nutrition.get('calories'), 0)}",
        f"Fat / Lipides {fmt(nutrition.get('total_fat_g'))}g   {fmt(pct_dv(nutrition, 'total_fat_g', CANADA_DV), 0)}% DV",
        f"  Saturated / saturés {fmt(nutrition.get('saturated_fat_g'))}g",
        f"  Trans / trans {fmt(nutrition.get('trans_fat_g'))}g",
        f"Carbohydrate / Glucides {fmt(nutrition.get('total_carbs_g'))}g",
        f"  Fibre {fmt(nutrition.get('dietary_fiber_g'))}g   {fmt(pct_dv(nutrition, 'dietary_fiber_g', CANADA_DV), 0)}% DV",
        f"  Sugars / Sucres {fmt(nutrition.get('total_sugars_g'))}g   {fmt(pct_dv(nutrition, 'total_sugars_g', CANADA_DV), 0)}% DV",
        f"Protein / Protéines {fmt(nutrition.get('protein_g'))}g",
        f"Cholesterol / Cholestérol {fmt(nutrition.get('cholesterol_mg'), 0)}mg",
        f"Sodium {fmt(nutrition.get('sodium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'sodium_mg', CANADA_DV), 0)}% DV",
        "--------------------------------",
        f"Potassium {fmt(nutrition.get('potassium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'potassium_mg', CANADA_DV), 0)}% DV",
        f"Calcium {fmt(nutrition.get('calcium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'calcium_mg', CANADA_DV), 0)}% DV",
        f"Iron / Fer {fmt(nutrition.get('iron_mg'))}mg   {fmt(pct_dv(nutrition, 'iron_mg', CANADA_DV), 0)}% DV",
        "",
        "Preview only — not a legal/compliance approval. Confirm bilingual formatting, rounding, and front-of-package rules before commercial use.",
    ]
    return "\n".join(lines)


def uk_nutrition_panel(name, nutrition, serving_size="1 serving", per_100_factor=None):
    # If per_100_factor is supplied, it scales serving values to an approximate per-100g basis.
    per_100 = scale_nutrition(nutrition, per_100_factor) if per_100_factor else None

    def uk_line(label, field, unit="g"):
        serving_val = salt_from_sodium_mg(nutrition.get(field)) if field == "sodium_mg" else nutrition.get(field)
        per100_val = None
        if per_100:
            per100_val = salt_from_sodium_mg(per_100.get(field)) if field == "sodium_mg" else per_100.get(field)
        nutrient_name = "Salt" if field == "sodium_mg" else label
        per100_text = fmt(per100_val) if per100_val is not None else "—"
        return f"{nutrient_name:<20} Per 100g: {per100_text}{unit}   Per serving: {fmt(serving_val)}{unit}"

    lines = [
        "NUTRITION INFORMATION — UK PREVIEW",
        f"{name}",
        f"Serving size {serving_size}",
        "--------------------------------",
        f"Energy              Per 100g: {'—' if not per_100 else fmt(per_100.get('calories'), 0)}kcal   Per serving: {fmt(nutrition.get('calories'), 0)}kcal",
        uk_line("Fat", "total_fat_g", "g"),
        uk_line("of which saturates", "saturated_fat_g", "g"),
        uk_line("Carbohydrate", "total_carbs_g", "g"),
        uk_line("of which sugars", "total_sugars_g", "g"),
        uk_line("Protein", "protein_g", "g"),
        uk_line("Salt", "sodium_mg", "g"),
        "",
        "Preview only — not a legal/compliance approval. Confirm per-100g/per-serving values, rounding, and UK/EU rules before commercial use.",
    ]
    return "\n".join(lines)


def make_label(region, name, nutrition, serving_size, per_100_factor=None):
    if region == "US":
        return us_nutrition_panel(name, nutrition, serving_size)
    if region == "Canada":
        return canada_nutrition_panel(name, nutrition, serving_size)
    return uk_nutrition_panel(name, nutrition, serving_size, per_100_factor)

# -----------------------------
# USDA helper
# -----------------------------
def search_usda_foods(query, api_key):
    if not requests:
        return []
    if not api_key:
        return []
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {"api_key": api_key, "query": query, "pageSize": 10}
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json().get("foods", [])
    except Exception as exc:
        st.warning(f"USDA lookup failed: {exc}")
        return []


def usda_food_to_product(food):
    nutrients = {key: None for key in NUTRIENT_FIELDS}
    nutrient_map = {
        "Energy": "calories",
        "Protein": "protein_g",
        "Total lipid (fat)": "total_fat_g",
        "Fatty acids, total saturated": "saturated_fat_g",
        "Carbohydrate, by difference": "total_carbs_g",
        "Fiber, total dietary": "dietary_fiber_g",
        "Sugars, total including NLEA": "total_sugars_g",
        "Sodium, Na": "sodium_mg",
        "Cholesterol": "cholesterol_mg",
        "Calcium, Ca": "calcium_mg",
        "Iron, Fe": "iron_mg",
        "Potassium, K": "potassium_mg",
        "Vitamin D (D2 + D3)": "vitamin_d_mcg",
    }
    for nutrient in food.get("foodNutrients", []):
        name = nutrient.get("nutrientName")
        if name in nutrient_map:
            nutrients[nutrient_map[name]] = to_float(nutrient.get("value"))

    description = food.get("description", "USDA Food")
    product = {
        "id": f"U{food.get('fdcId', len(st.session_state.products)+1)}",
        "name": description.title(),
        "supplier": "USDA FoodData Central",
        "ingredients": [],
        "allergens": [],
        "nutrition": nutrients,
        "raw_text": str(food),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "confidence": 80,
    }
    return product

# -----------------------------
# Demo data
# -----------------------------
def load_demo_data():
    samples = [
        (
            "Wheat Dinner Roll",
            "Supplier A",
            """Ingredients: wheat flour, sugar, salt, soy lecithin
Nutrition: Calories 120 Total Fat 2g Saturated Fat 0.5g Trans Fat 0g Cholesterol 0mg Sodium 200mg Total Carbohydrate 24g Dietary Fiber 1g Total Sugars 3g Added Sugars 2g Protein 4g Vitamin D 0mcg Calcium 20mg Iron 1.2mg Potassium 55mg""",
        ),
        (
            "Almond Protein Bite",
            "Supplier B",
            """Ingredients: almond flour, peanut butter, honey, whey protein, cocoa
Nutrition: Calories 180 Total Fat 9g Saturated Fat 2g Trans Fat 0g Cholesterol 10mg Sodium 85mg Total Carbohydrate 18g Dietary Fiber 3g Total Sugars 9g Added Sugars 6g Protein 8g Calcium 60mg Iron 1mg Potassium 180mg Magnesium 40mg Zinc 1.1mg""",
        ),
        (
            "Coconut Rice Cup",
            "Supplier C",
            """Ingredients: rice, coconut milk, salt
Nutrition: Calories 210 Total Fat 6g Saturated Fat 5g Sodium 140mg Total Carbohydrate 35g Dietary Fiber 2g Total Sugars 1g Protein 4g Calcium 15mg Iron 0.8mg Potassium 90mg""",
        ),
    ]
    st.session_state.products = [parse_product(text, name, supplier) for name, supplier, text in samples]

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.header("Demo Controls")
    if st.button("Load Demo Products"):
        load_demo_data()
        st.success("Demo products loaded.")
        st.rerun()

    if st.button("Clear All Products"):
        st.session_state.products = []
        st.session_state.recipes = []
        st.session_state.usda_results = []
        st.success("Cleared.")
        st.rerun()

    st.markdown("---")
    st.write("Current products:", len(st.session_state.products))
    st.write("Saved recipes:", len(st.session_state.recipes))

# -----------------------------
# Main tabs
# -----------------------------
tabs = st.tabs([
    "Dashboard",
    "Add Product",
    "USDA Lookup",
    "Search",
    "Product Detail",
    "Recipe Builder",
    "Nutrition Panels",
    "Export",
])

with tabs[0]:
    st.header("Dashboard")
    products = st.session_state.products
    total_products = len(products)
    total_allergen_products = sum(1 for p in products if p["allergens"])
    suppliers = len(set(p["supplier"] for p in products if p["supplier"]))
    avg_confidence = round(sum(p.get("confidence", 0) for p in products) / total_products, 1) if total_products else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Products", total_products)
    c2.metric("Products with Allergens", total_allergen_products)
    c3.metric("Suppliers", suppliers)
    c4.metric("Avg Extraction Confidence", f"{avg_confidence}%")

    if products:
        st.subheader("Product Database")
        st.dataframe(products_dataframe(products), use_container_width=True)

        st.subheader("Allergen Summary")
        allergen_counts = {}
        for p in products:
            for allergen in p["allergens"]:
                allergen_counts[allergen] = allergen_counts.get(allergen, 0) + 1
        if allergen_counts:
            st.bar_chart(pd.DataFrame.from_dict(allergen_counts, orient="index", columns=["count"]))
        else:
            st.info("No allergens detected yet.")
    else:
        st.info("No products yet. Use Add Product or load demo products from the sidebar.")

with tabs[1]:
    st.header("Add Product Specification")
    name = st.text_input("Product Name", placeholder="Example: Wheat Dinner Roll")
    supplier = st.text_input("Supplier", placeholder="Example: Supplier A")

    uploaded = st.file_uploader("Upload TXT or PDF", type=["txt", "pdf"])
    uploaded_text = extract_text_from_upload(uploaded)

    default_text = """Ingredients: wheat flour, sugar, salt, soy lecithin
Nutrition: Calories 120 Total Fat 2g Saturated Fat 0.5g Trans Fat 0g Cholesterol 0mg Sodium 200mg Total Carbohydrate 24g Dietary Fiber 1g Total Sugars 3g Added Sugars 2g Protein 4g Vitamin D 0mcg Calcium 20mg Iron 1.2mg Potassium 55mg"""

    text = st.text_area("Paste or review product specification text", value=uploaded_text if uploaded_text else default_text, height=260)

    if st.button("Parse and Save Product"):
        if not name.strip():
            st.warning("Please add a product name.")
        else:
            product = parse_product(text, name, supplier)
            st.session_state.products.append(product)
            st.success(f"Saved {name}")
            st.json(product)

with tabs[2]:
    st.header("USDA FoodData Central Lookup")
    st.caption("Search USDA FoodData Central by ingredient keyword, preview nutrients, and import selected foods into your product list.")

    saved_api_key = ""
    try:
        saved_api_key = st.secrets.get("USDA_API_KEY", "")
    except Exception:
        saved_api_key = ""

    if saved_api_key:
        st.success("USDA API key detected from Streamlit Secrets.")
        api_key = saved_api_key
    else:
        st.info("No USDA_API_KEY found in Streamlit Secrets yet. You can paste one below for temporary testing.")
        api_key = st.text_input("Temporary USDA API Key", type="password", help="For permanent use, add USDA_API_KEY in Streamlit Cloud Secrets.")

    query = st.text_input("Search USDA food by keyword", placeholder="Example: wheat flour, chicken breast, almond flour, milk")

    c1, c2 = st.columns([1, 1])
    with c1:
        page_size = st.slider("Number of results", min_value=5, max_value=25, value=10, step=5)
    with c2:
        data_type = st.selectbox("USDA data type", ["All", "Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"], index=0)

    def search_usda_foods_enhanced(query, api_key, page_size=10, data_type="All"):
        if not requests or not api_key or not query:
            return []
        url = "https://api.nal.usda.gov/fdc/v1/foods/search"
        params = {"api_key": api_key, "query": query, "pageSize": page_size}
        if data_type != "All":
            params["dataType"] = [data_type]
        try:
            response = requests.get(url, params=params, timeout=20)
            response.raise_for_status()
            return response.json().get("foods", [])
        except Exception as exc:
            st.warning(f"USDA lookup failed: {exc}")
            return []

    if st.button("Search USDA"):
        if not api_key:
            st.warning("Add your free USDA API key to search live USDA data.")
        elif not query.strip():
            st.warning("Enter a food search term.")
        else:
            with st.spinner("Searching USDA FoodData Central..."):
                st.session_state.usda_results = search_usda_foods_enhanced(query, api_key, page_size, data_type)
            if not st.session_state.usda_results:
                st.info("No USDA results found for that search.")

    if st.session_state.usda_results:
        st.subheader("Search Results")
        result_rows = []
        for food in st.session_state.usda_results:
            result_rows.append({
                "FDC ID": food.get("fdcId"),
                "Description": food.get("description"),
                "Data Type": food.get("dataType"),
                "Brand": food.get("brandOwner") or food.get("brandName") or "",
            })
        st.dataframe(pd.DataFrame(result_rows), use_container_width=True)

        options = [f"{food.get('description', 'Food')} — FDC {food.get('fdcId')}" for food in st.session_state.usda_results]
        selected = st.selectbox("Select a USDA food to preview/import", options)
        idx = options.index(selected)
        food = st.session_state.usda_results[idx]

        st.write("**Description:**", food.get("description"))
        st.write("**Data type:**", food.get("dataType", "Unknown"))
        if food.get("brandOwner") or food.get("brandName"):
            st.write("**Brand:**", food.get("brandOwner") or food.get("brandName"))

        nutrient_preview = pd.DataFrame(food.get("foodNutrients", []))
        if not nutrient_preview.empty:
            display_cols = [c for c in ["nutrientName", "value", "unitName"] if c in nutrient_preview.columns]
            st.dataframe(nutrient_preview[display_cols], use_container_width=True)

        imported_product = usda_food_to_product(food)
        with st.expander("Mapped product nutrition preview"):
            st.json(imported_product["nutrition"])

        custom_name = st.text_input("Product name to import", value=imported_product["name"])
        if st.button("Import Selected USDA Food as Product"):
            imported_product["name"] = custom_name.strip() or imported_product["name"]
            st.session_state.products.append(imported_product)
            st.success("USDA food imported as product.")
            st.rerun()

    with st.expander("How to add your USDA API key permanently"):
        st.markdown('''
1. Get a free key from USDA FoodData Central.
2. Open Streamlit Cloud → your app → Settings → Secrets.
3. Add this line and save:

```toml
USDA_API_KEY = "paste_your_key_here"
```

Then reboot/redeploy the app.
''')

with tabs[3]:
    st.header("Search Products")
    if not st.session_state.products:
        st.info("Add products first.")
    else:
        query = st.text_input("Search ingredient, allergen, product, supplier, or nutrient name")
        exclude_allergens = st.multiselect("Exclude allergens", ["gluten", "dairy", "soy", "egg", "peanut", "tree nuts", "fish", "shellfish", "sesame"])

        c1, c2, c3 = st.columns(3)
        with c1:
            max_sodium = st.number_input("Max sodium mg", min_value=0, value=2000)
        with c2:
            min_protein = st.number_input("Min protein g", min_value=0, value=0)
        with c3:
            max_calories = st.number_input("Max calories", min_value=0, value=9999)

        results = []
        for p in st.session_state.products:
            searchable = " ".join([
                p["name"],
                p["supplier"],
                " ".join(p["ingredients"]),
                " ".join(p["allergens"]),
                " ".join(k for k, v in p["nutrition"].items() if v is not None),
            ]).lower()
            if (
                (not query or query.lower() in searchable)
                and not any(a in p["allergens"] for a in exclude_allergens)
                and nutrition_value(p, "sodium_mg") <= max_sodium
                and nutrition_value(p, "protein_g") >= min_protein
                and nutrition_value(p, "calories") <= max_calories
            ):
                results.append(p)
        st.dataframe(products_dataframe(results), use_container_width=True)

with tabs[4]:
    st.header("Product Detail")
    if not st.session_state.products:
        st.info("Add products first.")
    else:
        selected_name = st.selectbox("Select product", [p["name"] for p in st.session_state.products])
        product = next(p for p in st.session_state.products if p["name"] == selected_name)
        c1, c2 = st.columns([1, 1])
        with c1:
            st.subheader(product["name"])
            st.write("Supplier:", product["supplier"] or "Not provided")
            st.write("Confidence:", f"{product.get('confidence', 0)}%")
            st.write("Allergens:", ", ".join(product["allergens"]) if product["allergens"] else "None")
            st.write("Ingredients:")
            st.write(product["ingredients"])
        with c2:
            st.subheader("Nutrition")
            st.dataframe(detailed_nutrition_dataframe(product["nutrition"]), use_container_width=True)
        with st.expander("Raw Extracted Text"):
            st.write(product["raw_text"])
        if st.button("Delete This Product"):
            st.session_state.products = [p for p in st.session_state.products if p["name"] != selected_name]
            st.success(f"Deleted {selected_name}")
            st.rerun()

with tabs[5]:
    st.header("Recipe Builder")
    if not st.session_state.products:
        st.info("Add products first.")
    else:
        recipe_name = st.text_input("Recipe Name", placeholder="Example: Lunch Bowl")
        selected_names = st.multiselect("Choose products", [p["name"] for p in st.session_state.products])

        total = {field: 0 for field in NUTRIENT_FIELDS}
        allergens = set()
        recipe_rows = []

        for name in selected_names:
            product = next(p for p in st.session_state.products if p["name"] == name)
            qty = st.number_input(f"Quantity for {name}", min_value=0.0, value=1.0, step=0.5)
            for key in total:
                total[key] += nutrition_value(product, key) * qty
            allergens.update(product["allergens"])
            recipe_rows.append({
                "Product": name,
                "Quantity": qty,
                "Calories": nutrition_value(product, "calories") * qty,
                "Protein (g)": nutrition_value(product, "protein_g") * qty,
                "Total Fat (g)": nutrition_value(product, "total_fat_g") * qty,
                "Carbs (g)": nutrition_value(product, "total_carbs_g") * qty,
                "Sodium (mg)": nutrition_value(product, "sodium_mg") * qty,
            })

        if selected_names:
            st.subheader("Recipe Items")
            st.dataframe(pd.DataFrame(recipe_rows), use_container_width=True)

            st.subheader("Batch Nutrition Totals")
            st.json({k: round(v, 2) for k, v in total.items() if v})

            c1, c2 = st.columns(2)
            with c1:
                servings = st.number_input("Number of servings / portions", min_value=1.0, value=1.0, step=0.5)
            with c2:
                portion_description = st.text_input("Portion description", value="1 serving")

            per_serving = {k: round(v / servings, 3) for k, v in total.items()}
            st.subheader("Nutrition Per Portion")
            st.dataframe(detailed_nutrition_dataframe(per_serving), use_container_width=True)

            if allergens:
                st.error("Allergen warning: " + ", ".join(sorted(allergens)))
            else:
                st.success("No allergens detected.")

            if st.button("Save Recipe"):
                st.session_state.recipes.append({
                    "name": recipe_name or f"Recipe {len(st.session_state.recipes) + 1}",
                    "items": recipe_rows,
                    "servings": servings,
                    "portion_description": portion_description,
                    "nutrition_totals": {k: round(v, 3) for k, v in total.items()},
                    "nutrition_per_serving": per_serving,
                    "allergens": sorted(allergens),
                    "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                })
                st.success("Recipe saved.")

        if st.session_state.recipes:
            st.subheader("Saved Recipes")
            st.dataframe(recipes_dataframe(st.session_state.recipes), use_container_width=True)

with tabs[6]:
    st.header("Nutrition Facts Panel Generator")
    st.caption("Generates preview labels from a product or saved recipe. This is a preview tool, not legal label approval.")

    sources = []
    for p in st.session_state.products:
        sources.append((f"Product: {p['name']}", p["name"], p["nutrition"], "1 serving"))
    for r in st.session_state.recipes:
        sources.append((f"Recipe: {r['name']}", r["name"], r.get("nutrition_per_serving", {}), r.get("portion_description", "1 serving")))

    if not sources:
        st.info("Add products or save a recipe first.")
    else:
        selected_source = st.selectbox("Choose product or recipe", [s[0] for s in sources])
        source = next(s for s in sources if s[0] == selected_source)
        region = st.selectbox("Label region", ["US", "Canada", "UK"])
        serving_size = st.text_input("Serving size text", value=source[3])

        per_100_factor = None
        if region == "UK":
            serving_grams = st.number_input("Serving grams for UK per-100g estimate", min_value=0.0, value=0.0, step=1.0)
            per_100_factor = 100 / serving_grams if serving_grams else None

        label = make_label(region, source[1], source[2], serving_size, per_100_factor)
        st.text_area("Panel Preview", value=label, height=420)
        st.download_button("Download Nutrition Panel TXT", data=label, file_name=f"{source[1]}_{region}_nutrition_panel.txt", mime="text/plain")

        st.subheader("Compliance Review Table")
        st.dataframe(compliance_export_dataframe(source[1], source[2], region), use_container_width=True)

with tabs[7]:
    st.header("Export Data")
    if not st.session_state.products and not st.session_state.recipes:
        st.info("No products or recipes to export.")
    else:
        region = st.selectbox("Compliance export profile", ["US", "Canada", "UK"])

        if st.session_state.products:
            st.download_button(
                label="Download Product Database CSV",
                data=products_dataframe(st.session_state.products).to_csv(index=False),
                file_name="food_product_database.csv",
                mime="text/csv",
            )

            st.download_button(
                label="Download Full Product Nutrition CSV",
                data=full_products_dataframe(st.session_state.products).to_csv(index=False),
                file_name="food_product_full_nutrition.csv",
                mime="text/csv",
            )

        if st.session_state.recipes:
            st.download_button(
                label="Download Recipes CSV",
                data=recipes_dataframe(st.session_state.recipes).to_csv(index=False),
                file_name="recipe_nutrition.csv",
                mime="text/csv",
            )

        excel_bytes = make_excel_export(st.session_state.products, st.session_state.recipes, region=region)
        st.download_button(
            label=f"Download Excel Workbook ({region} review)",
            data=excel_bytes,
            file_name=f"food_intelligence_{region.lower()}_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
