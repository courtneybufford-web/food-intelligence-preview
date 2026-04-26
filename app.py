import io
import re
from datetime import datetime

import pandas as pd
import streamlit as st

try:
    import requests
except Exception:
    requests = None

st.set_page_config(page_title="Food Intelligence Platform", layout="wide")
st.title("Food Intelligence Platform — MVP Preview")
st.caption("Products, ingredients, USDA/Open Food Facts search, nested recipes/subrecipes, nutrition panels, copy-ready labels, and exports.")

# -----------------------------
# Session state
# -----------------------------
for key, default in {
    "products": [],
    "recipes": [],
    "database_results": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# -----------------------------
# Nutrients, units, allergens
# -----------------------------
NUTRIENT_DEFINITIONS = {
    "calories": ("Calories", "kcal"),
    "total_fat_g": ("Total Fat", "g"),
    "saturated_fat_g": ("Saturated Fat", "g"),
    "trans_fat_g": ("Trans Fat", "g"),
    "cholesterol_mg": ("Cholesterol", "mg"),
    "sodium_mg": ("Sodium", "mg"),
    "total_carbs_g": ("Total Carbohydrate", "g"),
    "dietary_fiber_g": ("Dietary Fiber", "g"),
    "total_sugars_g": ("Total Sugars", "g"),
    "added_sugars_g": ("Added Sugars", "g"),
    "protein_g": ("Protein", "g"),
    "vitamin_d_mcg": ("Vitamin D", "mcg"),
    "calcium_mg": ("Calcium", "mg"),
    "iron_mg": ("Iron", "mg"),
    "potassium_mg": ("Potassium", "mg"),
    "vitamin_a_mcg": ("Vitamin A", "mcg"),
    "vitamin_c_mg": ("Vitamin C", "mg"),
    "magnesium_mg": ("Magnesium", "mg"),
    "zinc_mg": ("Zinc", "mg"),
    "folate_mcg": ("Folate", "mcg"),
    "phosphorus_mg": ("Phosphorus", "mg"),
}
NUTRIENT_FIELDS = list(NUTRIENT_DEFINITIONS.keys())

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

COMMON_UNITS = {
    "g": {"label": "grams (g)", "gram_factor": 1, "reliable": True},
    "kg": {"label": "kilograms (kg)", "gram_factor": 1000, "reliable": True},
    "mg": {"label": "milligrams (mg)", "gram_factor": 0.001, "reliable": True},
    "oz": {"label": "ounces (oz)", "gram_factor": 28.3495, "reliable": True},
    "lb": {"label": "pounds (lb)", "gram_factor": 453.592, "reliable": True},
    "ml": {"label": "milliliters (ml)", "gram_factor": None, "reliable": False},
    "l": {"label": "liters (l)", "gram_factor": None, "reliable": False},
    "tsp": {"label": "teaspoons", "gram_factor": None, "reliable": False},
    "tbsp": {"label": "tablespoons", "gram_factor": None, "reliable": False},
    "cup": {"label": "cups", "gram_factor": None, "reliable": False},
    "fl_oz": {"label": "fluid ounces", "gram_factor": None, "reliable": False},
    "pint": {"label": "pints", "gram_factor": None, "reliable": False},
    "quart": {"label": "quarts", "gram_factor": None, "reliable": False},
    "gallon": {"label": "gallons", "gram_factor": None, "reliable": False},
    "each": {"label": "each", "gram_factor": None, "reliable": False},
    "piece": {"label": "piece", "gram_factor": None, "reliable": False},
    "slice": {"label": "slice", "gram_factor": None, "reliable": False},
    "serving": {"label": "serving", "gram_factor": None, "reliable": False},
    "portion": {"label": "portion", "gram_factor": None, "reliable": False},
    "case": {"label": "case", "gram_factor": None, "reliable": False},
    "bag": {"label": "bag", "gram_factor": None, "reliable": False},
    "can": {"label": "can", "gram_factor": None, "reliable": False},
}
UNIT_OPTIONS = list(COMMON_UNITS.keys())

UK_14_ALLERGEN_TERMS = {
    "celery": ["celery", "celeriac"],
    "cereals containing gluten": ["wheat", "rye", "barley", "oats", "spelt", "kamut", "gluten", "malt"],
    "crustaceans": ["crustacean", "prawn", "prawns", "crab", "lobster", "shrimp"],
    "eggs": ["egg", "eggs", "albumen", "albumin"],
    "fish": ["fish", "anchovy", "anchovies", "salmon", "tuna", "cod", "haddock"],
    "lupin": ["lupin", "lupine"],
    "milk": ["milk", "cheese", "butter", "cream", "whey", "casein", "caseinate", "lactose", "yoghurt", "yogurt"],
    "molluscs": ["mollusc", "mollusk", "mussels", "oyster", "oysters", "squid", "clam", "clams", "scallop", "scallops"],
    "mustard": ["mustard"],
    "peanuts": ["peanut", "peanuts", "groundnut", "groundnuts"],
    "sesame": ["sesame", "tahini"],
    "soybeans": ["soy", "soya", "soybean", "soybeans", "tofu", "edamame"],
    "sulphur dioxide and sulphites": ["sulphite", "sulphites", "sulfite", "sulfites", "sulphur dioxide", "sulfur dioxide", "e220", "e221", "e222", "e223", "e224", "e226", "e227", "e228"],
    "tree nuts": ["almond", "almonds", "hazelnut", "hazelnuts", "walnut", "walnuts", "cashew", "cashews", "pecan", "pecans", "brazil nut", "brazil nuts", "pistachio", "pistachios", "macadamia", "macadamias"],
}

# -----------------------------
# Helpers
# -----------------------------
def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def to_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def fmt(value, decimals=1):
    if value is None:
        return "—"
    try:
        v = float(value)
    except Exception:
        return str(value)
    if v.is_integer():
        return str(int(v))
    return f"{v:.{decimals}f}".rstrip("0").rstrip(".")


def empty_nutrition():
    return {field: None for field in NUTRIENT_FIELDS}


def add_nutrition(a, b, factor=1):
    out = dict(a)
    for key in NUTRIENT_FIELDS:
        av = out.get(key) or 0
        bv = b.get(key) if b else None
        if bv is not None:
            out[key] = round(av + (bv * factor), 4)
    return out


def scale_nutrition(nutrition, factor):
    out = {}
    for key in NUTRIENT_FIELDS:
        value = nutrition.get(key)
        out[key] = round(value * factor, 4) if value is not None else None
    return out


def pct_dv(nutrition, field, dv_map):
    value = nutrition.get(field)
    dv = dv_map.get(field)
    if value is None or not dv:
        return None
    return round(value / dv * 100)


def salt_from_sodium_mg(sodium_mg):
    if sodium_mg is None:
        return None
    return round((sodium_mg * 2.5) / 1000, 3)


def unit_label(unit):
    return COMMON_UNITS.get(unit, {"label": unit}).get("label", unit)


def gram_weight(amount, unit):
    meta = COMMON_UNITS.get(unit, {})
    factor = meta.get("gram_factor")
    if factor is None:
        return None
    return round((amount or 0) * factor, 4)


def unit_review_note(amount, unit):
    grams = gram_weight(amount, unit)
    if grams is None:
        return f"{fmt(amount)} {unit} needs manual review for predominance sorting because this unit needs density/piece-weight conversion."
    return ""


def display_name(obj):
    return obj.get("consumer_name") or obj.get("name") or obj.get("internal_name") or "Unnamed"


def internal_name(obj):
    return obj.get("internal_name") or obj.get("name") or obj.get("consumer_name") or "Unnamed"


def get_product(name):
    return next((p for p in st.session_state.products if internal_name(p) == name), None)


def get_recipe(name):
    return next((r for r in st.session_state.recipes if internal_name(r) == name), None)

# -----------------------------
# Parsing
# -----------------------------
def parse_nutrients(text):
    lower = text.lower()
    patterns = {
        "calories": r"\bcalories\b\D*(\d+(?:\.\d+)?)",
        "total_fat_g": r"\btotal\s+fat\b\D*(\d+(?:\.\d+)?)\s*g?",
        "saturated_fat_g": r"\bsaturated\s+fat\b\D*(\d+(?:\.\d+)?)\s*g?",
        "trans_fat_g": r"\btrans\s+fat\b\D*(\d+(?:\.\d+)?)\s*g?",
        "cholesterol_mg": r"\bcholesterol\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "sodium_mg": r"\bsodium\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "total_carbs_g": r"\b(?:total\s+carbohydrate|carbohydrate|carbs)\b\D*(\d+(?:\.\d+)?)\s*g?",
        "dietary_fiber_g": r"\b(?:dietary\s+fiber|fibre|fiber)\b\D*(\d+(?:\.\d+)?)\s*g?",
        "total_sugars_g": r"\b(?:total\s+sugars|sugars|sugar)\b\D*(\d+(?:\.\d+)?)\s*g?",
        "added_sugars_g": r"\badded\s+sugars\b\D*(\d+(?:\.\d+)?)\s*g?",
        "protein_g": r"\bprotein\b\D*(\d+(?:\.\d+)?)\s*g?",
        "vitamin_d_mcg": r"\bvitamin\s+d\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "calcium_mg": r"\bcalcium\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "iron_mg": r"\biron\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "potassium_mg": r"\bpotassium\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "vitamin_a_mcg": r"\bvitamin\s+a\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "vitamin_c_mg": r"\bvitamin\s+c\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "magnesium_mg": r"\bmagnesium\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "zinc_mg": r"\bzinc\b\D*(\d+(?:\.\d+)?)\s*mg?",
        "folate_mcg": r"\b(?:folate|folic\s+acid)\b\D*(\d+(?:\.\d+)?)\s*(?:mcg|µg)?",
        "phosphorus_mg": r"\bphosphorus\b\D*(\d+(?:\.\d+)?)\s*mg?",
    }
    nutrients = empty_nutrition()
    for key, pattern in patterns.items():
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        nutrients[key] = to_float(match.group(1)) if match else None
    return nutrients


def parse_ingredients(text):
    lower = text.lower()
    if "ingredients" not in lower:
        return []
    part = lower.split("ingredients", 1)[1]
    for stop in ["nutrition", "contains", "allergens", "allergen", "may contain", "distributed by", "manufactured by"]:
        if stop in part:
            part = part.split(stop, 1)[0]
    return [i.strip(" :.;\n\t") for i in re.split(r"[,;]", part) if i.strip(" :.;\n\t")]


def parse_allergens(text):
    lower = text.lower()
    rules = {
        "wheat": "gluten", "gluten": "gluten", "barley": "gluten", "rye": "gluten", "oats": "gluten",
        "milk": "dairy", "cheese": "dairy", "butter": "dairy", "cream": "dairy", "whey": "dairy", "casein": "dairy",
        "soy": "soy", "soya": "soy", "soybean": "soy", "egg": "egg", "peanut": "peanut",
        "almond": "tree nuts", "cashew": "tree nuts", "walnut": "tree nuts", "pecan": "tree nuts", "hazelnut": "tree nuts",
        "fish": "fish", "salmon": "fish", "tuna": "fish", "shellfish": "shellfish", "shrimp": "shellfish", "crab": "shellfish", "lobster": "shellfish", "sesame": "sesame",
    }
    return sorted({allergen for word, allergen in rules.items() if re.search(rf"\b{re.escape(word)}\b", lower)})


def confidence_score(product):
    score = 0
    if product.get("ingredients"):
        score += 35
    if product.get("allergens"):
        score += 10
    score += min(55, sum(1 for v in product.get("nutrition", {}).values() if v is not None) * 4)
    return min(100, score)


def parse_product(text, internal, consumer, supplier):
    product = {
        "id": f"P{len(st.session_state.products) + 1:04d}",
        "internal_name": clean_text(internal),
        "consumer_name": clean_text(consumer) or clean_text(internal),
        "name": clean_text(internal),
        "supplier": clean_text(supplier),
        "ingredients": parse_ingredients(text),
        "allergens": parse_allergens(text),
        "nutrition": parse_nutrients(text),
        "raw_text": text,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    product["confidence"] = confidence_score(product)
    return product

# -----------------------------
# Dataframes / exports
# -----------------------------
def detailed_nutrition_dataframe(nutrition):
    return pd.DataFrame([
        {"Nutrient Key": key, "Nutrient": NUTRIENT_DEFINITIONS[key][0], "Value": nutrition.get(key), "Unit": NUTRIENT_DEFINITIONS[key][1]}
        for key in NUTRIENT_FIELDS
    ])


def products_dataframe(products):
    rows = []
    for p in products:
        row = {
            "ID": p.get("id"),
            "Internal Name": internal_name(p),
            "Consumer Name": display_name(p),
            "Supplier": p.get("supplier", ""),
            "Ingredients": ", ".join(p.get("ingredients", [])),
            "Allergens": ", ".join(p.get("allergens", [])) if p.get("allergens") else "None",
            "Confidence": p.get("confidence", 0),
        }
        row.update(p.get("nutrition", {}))
        rows.append(row)
    return pd.DataFrame(rows)


def recipes_dataframe(recipes):
    rows = []
    for r in recipes:
        row = {
            "Internal Name": internal_name(r),
            "Consumer Name": display_name(r),
            "Servings": r.get("servings"),
            "Portion Description": r.get("portion_description"),
            "Allergens": ", ".join(r.get("allergens", [])),
            "Ingredient List": r.get("ingredient_list", ""),
            "Review Flags": "; ".join(r.get("review_flags", [])),
            "Created At": r.get("created_at", ""),
        }
        row.update({f"batch_{k}": v for k, v in r.get("nutrition_totals", {}).items()})
        row.update({f"per_serving_{k}": v for k, v in r.get("nutrition_per_serving", {}).items()})
        rows.append(row)
    return pd.DataFrame(rows)


def make_excel_export(region="US"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if st.session_state.products:
            products_dataframe(st.session_state.products).to_excel(writer, sheet_name="Products", index=False)
        if st.session_state.recipes:
            recipes_dataframe(st.session_state.recipes).to_excel(writer, sheet_name="Recipes", index=False)
    output.seek(0)
    return output.getvalue()

# -----------------------------
# External database search
# -----------------------------
def usda_api_key():
    try:
        return st.secrets.get("USDA_API_KEY", "")
    except Exception:
        return ""


def search_usda(query, page_size=50):
    key = usda_api_key()
    if not requests or not key or not query:
        return []
    try:
        response = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"api_key": key, "query": query, "pageSize": page_size},
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("foods", [])
    except Exception as exc:
        st.warning(f"USDA search failed: {exc}")
        return []


def usda_to_product(food):
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
    nutrition = empty_nutrition()
    for n in food.get("foodNutrients", []):
        field = nutrient_map.get(n.get("nutrientName"))
        if field:
            nutrition[field] = to_float(n.get("value"))
    name = (food.get("description") or "USDA Food").title()
    return {
        "id": f"U{food.get('fdcId', '')}",
        "internal_name": name,
        "consumer_name": name,
        "name": name,
        "supplier": "USDA FoodData Central",
        "ingredients": [],
        "allergens": [],
        "nutrition": nutrition,
        "raw_text": str(food),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "confidence": 80,
    }


def search_open_food_facts(query, page_size=50):
    if not requests or not query:
        return []
    try:
        response = requests.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": query,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": page_size,
                "fields": "code,product_name,generic_name,brands,ingredients_text,allergens,allergens_tags,nutriments",
            },
            headers={"User-Agent": "FoodIntelligencePreview/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("products", [])
    except Exception as exc:
        st.warning(f"Open Food Facts search failed: {exc}")
        return []


def off_to_product(item):
    nutriments = item.get("nutriments", {}) or {}

    def n(*keys):
        for key in keys:
            value = to_float(nutriments.get(key))
            if value is not None:
                return value
        return None

    nutrition = empty_nutrition()
    nutrition["calories"] = n("energy-kcal_100g", "energy-kcal_serving")
    nutrition["total_fat_g"] = n("fat_100g", "fat_serving")
    nutrition["saturated_fat_g"] = n("saturated-fat_100g", "saturated-fat_serving")
    nutrition["trans_fat_g"] = n("trans-fat_100g", "trans-fat_serving")
    nutrition["total_carbs_g"] = n("carbohydrates_100g", "carbohydrates_serving")
    nutrition["dietary_fiber_g"] = n("fiber_100g", "fiber_serving")
    nutrition["total_sugars_g"] = n("sugars_100g", "sugars_serving")
    nutrition["added_sugars_g"] = n("added-sugars_100g", "added-sugars_serving")
    nutrition["protein_g"] = n("proteins_100g", "proteins_serving")
    sodium_g = n("sodium_100g", "sodium_serving")
    salt_g = n("salt_100g", "salt_serving")
    if sodium_g is not None:
        nutrition["sodium_mg"] = round(sodium_g * 1000, 3)
    elif salt_g is not None:
        nutrition["sodium_mg"] = round((salt_g / 2.5) * 1000, 3)

    name = item.get("product_name") or item.get("generic_name") or "Open Food Facts Product"
    ingredients_text = item.get("ingredients_text") or ""
    brand = item.get("brands") or ""
    allergen_text = " ".join(item.get("allergens_tags", []) or []) + " " + (item.get("allergens") or "")
    return {
        "id": f"OFF{item.get('code', '')}",
        "internal_name": name.title(),
        "consumer_name": name.title(),
        "name": name.title(),
        "supplier": f"Open Food Facts{(' — ' + brand) if brand else ''}",
        "ingredients": [x.strip() for x in re.split(r"[,;]", ingredients_text.lower()) if x.strip()],
        "allergens": parse_allergens(allergen_text),
        "nutrition": nutrition,
        "raw_text": str(item),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "confidence": 70,
    }

# -----------------------------
# Recipes / ingredient list generation
# -----------------------------
def calculate_recipe(product_items, recipe_items, stack=None):
    stack = stack or []
    total = {k: 0 for k in NUTRIENT_FIELDS}
    allergens = set()
    components = []
    review_flags = []

    for item in product_items:
        product = get_product(item["name"])
        if not product:
            continue
        amount = item.get("amount", 1)
        unit = item.get("unit", "serving")
        total = add_nutrition(total, product.get("nutrition", {}), amount)
        allergens.update(product.get("allergens", []))
        grams = gram_weight(amount, unit)
        flag = unit_review_note(amount, unit)
        if flag:
            review_flags.append(f"{display_name(product)}: {flag}")
        components.append({
            "type": "product",
            "name": display_name(product),
            "internal_name": internal_name(product),
            "amount": amount,
            "unit": unit,
            "grams": grams,
            "ingredients": product.get("ingredients", []),
            "sort_weight": grams if grams is not None else -1,
        })

    for item in recipe_items:
        recipe_name = item["name"]
        if recipe_name in stack:
            raise ValueError("Circular recipe reference detected: " + " > ".join(stack + [recipe_name]))
        recipe = get_recipe(recipe_name)
        if not recipe:
            continue
        amount = item.get("amount", 1)
        unit = item.get("unit", "portion")
        sub_total, sub_allergens, sub_components, sub_flags = calculate_recipe(
            recipe.get("product_items", []),
            recipe.get("recipe_items", []),
            stack + [recipe_name],
        )
        total = add_nutrition(total, sub_total, amount)
        allergens.update(sub_allergens)
        grams = gram_weight(amount, unit)
        flag = unit_review_note(amount, unit)
        if flag:
            review_flags.append(f"{display_name(recipe)}: {flag}")
        review_flags.extend(sub_flags)
        components.append({
            "type": "subrecipe",
            "name": display_name(recipe),
            "internal_name": internal_name(recipe),
            "amount": amount,
            "unit": unit,
            "grams": grams,
            "sub_components": sub_components,
            "sort_weight": grams if grams is not None else -1,
        })

    return total, sorted(allergens), components, list(dict.fromkeys(review_flags))


def ingredient_component_text(component, include_subrecipes=True, sort_by_predominance=True, emphasize_allergens=False):
    name = component["name"]
    if component["type"] == "subrecipe" and include_subrecipes:
        sub_list, _ = make_ingredient_list_from_components(
            component.get("sub_components", []),
            include_subrecipes=True,
            sort_by_predominance=sort_by_predominance,
            emphasize_allergens=emphasize_allergens,
            include_prefix=False,
        )
        return f"{name} ({sub_list})" if sub_list else name
    return name


def emphasise_uk_allergens_in_text(text):
    terms = sorted({term for terms in UK_14_ALLERGEN_TERMS.values() for term in terms}, key=len, reverse=True)
    for term in terms:
        text = re.sub(rf"\b({re.escape(term)})\b", lambda m: m.group(1).upper(), text, flags=re.IGNORECASE)
    return text


def make_ingredient_list_from_components(components, include_subrecipes=True, sort_by_predominance=True, emphasize_allergens=False, include_prefix=True):
    comps = list(components)
    review_flags = []
    if sort_by_predominance:
        comps = sorted(comps, key=lambda c: c.get("sort_weight", -1), reverse=True)
        if any(c.get("grams") is None for c in comps):
            review_flags.append("Some items use volume/count units and need density or piece-weight review before final predominance order is used.")
    text = ", ".join(ingredient_component_text(c, include_subrecipes, sort_by_predominance, emphasize_allergens) for c in comps)
    if emphasize_allergens:
        text = emphasise_uk_allergens_in_text(text)
    if include_prefix:
        text = "Ingredients: " + text if text else "Ingredients: Not available."
    return text, review_flags


def detect_uk_allergens(text):
    found = []
    lower = (text or "").lower()
    for allergen, terms in UK_14_ALLERGEN_TERMS.items():
        if any(re.search(rf"\b{re.escape(term)}\b", lower) for term in terms):
            found.append(allergen)
    return sorted(set(found))

# -----------------------------
# Nutrition panels and copy text
# -----------------------------
def us_panel(name, nutrition, serving="1 serving"):
    return "\n".join([
        "NUTRITION FACTS — US PREVIEW",
        name,
        f"Serving size {serving}",
        "--------------------------------",
        f"Calories {fmt(nutrition.get('calories'), 0)}",
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
        f"Vitamin D {fmt(nutrition.get('vitamin_d_mcg'))}mcg   {fmt(pct_dv(nutrition, 'vitamin_d_mcg', US_DV), 0)}% DV",
        f"Calcium {fmt(nutrition.get('calcium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'calcium_mg', US_DV), 0)}% DV",
        f"Iron {fmt(nutrition.get('iron_mg'))}mg   {fmt(pct_dv(nutrition, 'iron_mg', US_DV), 0)}% DV",
        f"Potassium {fmt(nutrition.get('potassium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'potassium_mg', US_DV), 0)}% DV",
        "",
        "Preview only — not legal/compliance approval.",
    ])


def canada_panel(name, nutrition, serving="1 serving"):
    return "\n".join([
        "NUTRITION FACTS / VALEUR NUTRITIVE — CANADA PREVIEW",
        name,
        f"Serving size / Portion {serving}",
        "--------------------------------",
        f"Calories {fmt(nutrition.get('calories'), 0)}",
        f"Fat / Lipides {fmt(nutrition.get('total_fat_g'))}g   {fmt(pct_dv(nutrition, 'total_fat_g', CANADA_DV), 0)}% DV",
        f"Saturated / saturés {fmt(nutrition.get('saturated_fat_g'))}g",
        f"Trans / trans {fmt(nutrition.get('trans_fat_g'))}g",
        f"Carbohydrate / Glucides {fmt(nutrition.get('total_carbs_g'))}g",
        f"Fibre {fmt(nutrition.get('dietary_fiber_g'))}g   {fmt(pct_dv(nutrition, 'dietary_fiber_g', CANADA_DV), 0)}% DV",
        f"Sugars / Sucres {fmt(nutrition.get('total_sugars_g'))}g   {fmt(pct_dv(nutrition, 'total_sugars_g', CANADA_DV), 0)}% DV",
        f"Protein / Protéines {fmt(nutrition.get('protein_g'))}g",
        f"Cholesterol / Cholestérol {fmt(nutrition.get('cholesterol_mg'), 0)}mg",
        f"Sodium {fmt(nutrition.get('sodium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'sodium_mg', CANADA_DV), 0)}% DV",
        f"Potassium {fmt(nutrition.get('potassium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'potassium_mg', CANADA_DV), 0)}% DV",
        f"Calcium {fmt(nutrition.get('calcium_mg'), 0)}mg   {fmt(pct_dv(nutrition, 'calcium_mg', CANADA_DV), 0)}% DV",
        f"Iron / Fer {fmt(nutrition.get('iron_mg'))}mg   {fmt(pct_dv(nutrition, 'iron_mg', CANADA_DV), 0)}% DV",
        "",
        "Preview only — not legal/compliance approval.",
    ])


def uk_panel(name, nutrition, serving="1 serving"):
    salt_g = salt_from_sodium_mg(nutrition.get("sodium_mg"))
    return "\n".join([
        "NUTRITION INFORMATION — UK PREVIEW",
        name,
        f"Serving size {serving}",
        "--------------------------------",
        f"Energy {fmt(nutrition.get('calories'), 0)} kcal",
        f"Fat {fmt(nutrition.get('total_fat_g'))}g",
        f"of which saturates {fmt(nutrition.get('saturated_fat_g'))}g",
        f"Carbohydrate {fmt(nutrition.get('total_carbs_g'))}g",
        f"of which sugars {fmt(nutrition.get('total_sugars_g'))}g",
        f"Protein {fmt(nutrition.get('protein_g'))}g",
        f"Salt {fmt(salt_g)}g",
        "",
        "Preview only — not legal/compliance approval.",
    ])


def make_panel(region, name, nutrition, serving):
    if region == "US":
        return us_panel(name, nutrition, serving)
    if region == "Canada":
        return canada_panel(name, nutrition, serving)
    return uk_panel(name, nutrition, serving)


def source_options():
    sources = []
    for p in st.session_state.products:
        components = [{"type": "product", "name": display_name(p), "amount": 1, "unit": "serving", "grams": None, "sort_weight": -1, "ingredients": p.get("ingredients", [])}]
        ingredients = ", ".join(p.get("ingredients", []))
        sources.append({
            "type": "Product",
            "internal_name": internal_name(p),
            "consumer_name": display_name(p),
            "nutrition": p.get("nutrition", {}),
            "serving": "1 serving",
            "ingredients_text": f"Ingredients: {ingredients}" if ingredients else "Ingredients: Not available.",
            "allergens": p.get("allergens", []),
            "components": components,
        })
    for r in st.session_state.recipes:
        sources.append({
            "type": "Recipe",
            "internal_name": internal_name(r),
            "consumer_name": display_name(r),
            "nutrition": r.get("nutrition_per_serving", {}),
            "serving": r.get("portion_description", "1 serving"),
            "ingredients_text": r.get("ingredient_list", "Ingredients: Not available."),
            "allergens": r.get("allergens", []),
            "components": r.get("components", []),
        })
    return sources


def allergen_declaration(source, region):
    name = source["consumer_name"]
    if region == "UK":
        detected = detect_uk_allergens(source.get("ingredients_text", ""))
        if detected:
            return f"{name}\n\nAllergen declaration: Contains {', '.join(detected)}. Review required for PPDS/Natasha's Law."
        return f"{name}\n\nAllergen declaration: No UK 14 allergens automatically detected. Review before use."
    allergens = source.get("allergens", [])
    if allergens:
        return f"{name}\n\nContains: {', '.join(sorted(set(allergens)))}"
    return f"{name}\n\nContains: No allergens automatically detected. Review before use."

# -----------------------------
# Demo data
# -----------------------------
def load_demo_data():
    samples = [
        ("ROLL-001", "Wheat Dinner Roll", "Demo Supplier", "Ingredients: wheat flour, sugar, salt, soy lecithin\nNutrition: Calories 120 Total Fat 2g Saturated Fat 0.5g Sodium 200mg Total Carbohydrate 24g Dietary Fiber 1g Total Sugars 3g Added Sugars 2g Protein 4g Calcium 20mg Iron 1.2mg Potassium 55mg"),
        ("CHICK-001", "Chicken Breast", "Demo Supplier", "Ingredients: chicken breast, water, salt\nNutrition: Calories 165 Total Fat 3.6g Saturated Fat 1g Sodium 74mg Total Carbohydrate 0g Protein 31g Potassium 256mg"),
        ("AIOLI-001", "Garlic Aioli", "Demo Supplier", "Ingredients: mayonnaise, egg yolk, garlic, lemon juice, mustard\nNutrition: Calories 100 Total Fat 11g Saturated Fat 1.5g Sodium 90mg Total Carbohydrate 1g Protein 0g"),
    ]
    st.session_state.products = [parse_product(text, internal, consumer, supplier) for internal, consumer, supplier, text in samples]
    st.session_state.recipes = []

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.header("Demo Controls")
    if st.button("Load Demo Products"):
        load_demo_data()
        st.success("Demo products loaded.")
        st.rerun()
    if st.button("Clear All"):
        st.session_state.products = []
        st.session_state.recipes = []
        st.session_state.database_results = []
        st.success("Cleared.")
        st.rerun()
    st.markdown("---")
    st.write("Products:", len(st.session_state.products))
    st.write("Recipes:", len(st.session_state.recipes))
    if not usda_api_key():
        st.info("Optional: add USDA_API_KEY in Streamlit Secrets for USDA search.")

# -----------------------------
# UI
# -----------------------------
tabs = st.tabs([
    "Dashboard",
    "Add Product",
    "Database Search",
    "Product Detail",
    "Recipe Builder",
    "Nutrition Panels",
    "Copy Center",
    "UK PPDS Review",
    "Export",
])

with tabs[0]:
    st.header("Dashboard")
    c1, c2, c3 = st.columns(3)
    c1.metric("Products", len(st.session_state.products))
    c2.metric("Recipes", len(st.session_state.recipes))
    c3.metric("Allergen Products", sum(1 for p in st.session_state.products if p.get("allergens")))
    if st.session_state.products:
        st.dataframe(products_dataframe(st.session_state.products), use_container_width=True)
    if st.session_state.recipes:
        st.subheader("Saved Recipes")
        st.dataframe(recipes_dataframe(st.session_state.recipes), use_container_width=True)

with tabs[1]:
    st.header("Add Product / Ingredient")
    internal = st.text_input("Internal name / SKU", placeholder="Example: ROLL-001")
    consumer = st.text_input("Consumer-facing name", placeholder="Example: Wheat Dinner Roll")
    supplier = st.text_input("Supplier", placeholder="Example: Supplier A")
    default_text = "Ingredients: wheat flour, sugar, salt, soy lecithin\nNutrition: Calories 120 Total Fat 2g Saturated Fat 0.5g Sodium 200mg Total Carbohydrate 24g Dietary Fiber 1g Total Sugars 3g Added Sugars 2g Protein 4g Calcium 20mg Iron 1.2mg Potassium 55mg"
    text = st.text_area("Paste product specification text", value=default_text, height=220)
    if st.button("Parse and Save Product"):
        if not internal and not consumer:
            st.warning("Add at least an internal or consumer-facing name.")
        else:
            product = parse_product(text, internal or consumer, consumer or internal, supplier)
            st.session_state.products.append(product)
            st.success(f"Saved {display_name(product)}")
            st.json(product)

with tabs[2]:
    st.header("Database Search")
    query = st.text_input("Search USDA and Open Food Facts", placeholder="Example: wheat flour")
    c1, c2, c3 = st.columns(3)
    use_usda = c1.checkbox("USDA", value=True)
    use_off = c2.checkbox("Open Food Facts", value=True)
    page_size = c3.number_input("Results per source", min_value=10, max_value=100, value=50, step=10)
    if st.button("Search Databases") and query:
        results = []
        if use_usda:
            for item in search_usda(query, page_size=page_size):
                results.append(usda_to_product(item))
        if use_off:
            for item in search_open_food_facts(query, page_size=page_size):
                results.append(off_to_product(item))
        st.session_state.database_results = results
    if st.session_state.database_results:
        st.dataframe(products_dataframe(st.session_state.database_results), use_container_width=True)
        choice = st.selectbox("Import result as product", [internal_name(p) for p in st.session_state.database_results])
        if st.button("Import Selected Result"):
            selected = next(p for p in st.session_state.database_results if internal_name(p) == choice)
            selected = dict(selected)
            selected["id"] = f"P{len(st.session_state.products) + 1:04d}"
            st.session_state.products.append(selected)
            st.success("Imported.")
            st.rerun()

with tabs[3]:
    st.header("Product Detail")
    if not st.session_state.products:
        st.info("Add products first.")
    else:
        choice = st.selectbox("Select product", [internal_name(p) for p in st.session_state.products])
        p = get_product(choice)
        c1, c2 = st.columns(2)
        with c1:
            st.write("Internal name:", internal_name(p))
            st.write("Consumer-facing name:", display_name(p))
            st.write("Supplier:", p.get("supplier"))
            st.write("Allergens:", ", ".join(p.get("allergens", [])) if p.get("allergens") else "None")
            st.write("Ingredients:", p.get("ingredients", []))
        with c2:
            st.dataframe(detailed_nutrition_dataframe(p.get("nutrition", {})), use_container_width=True)
        if st.button("Delete Product"):
            st.session_state.products = [x for x in st.session_state.products if internal_name(x) != choice]
            st.success("Deleted.")
            st.rerun()

with tabs[4]:
    st.header("Recipe Builder with Subrecipes")
    if not st.session_state.products:
        st.info("Add products first.")
    else:
        internal = st.text_input("Recipe internal name", placeholder="Example: SANDWICH-BASE")
        consumer = st.text_input("Recipe consumer-facing name", placeholder="Example: Chicken Sandwich")
        c1, c2 = st.columns(2)
        servings = c1.number_input("Number of servings", min_value=1.0, value=1.0, step=0.5)
        portion_description = c2.text_input("Portion description", value="1 serving")

        st.subheader("Add Products / Ingredients")
        selected_products = st.multiselect("Products", [internal_name(p) for p in st.session_state.products])
        product_items = []
        for name in selected_products:
            c1, c2 = st.columns(2)
            amount = c1.number_input(f"Amount for {name}", min_value=0.0, value=1.0, step=0.25, key=f"prod_amt_{name}")
            unit = c2.selectbox(f"Unit for {name}", UNIT_OPTIONS, index=UNIT_OPTIONS.index("g") if "g" in UNIT_OPTIONS else 0, key=f"prod_unit_{name}")
            product_items.append({"name": name, "amount": amount, "unit": unit})

        st.subheader("Add Saved Recipes / Subrecipes")
        available_recipes = [internal_name(r) for r in st.session_state.recipes if internal_name(r) != internal]
        selected_recipes = st.multiselect("Subrecipes", available_recipes)
        recipe_items = []
        for name in selected_recipes:
            c1, c2 = st.columns(2)
            amount = c1.number_input(f"Amount for subrecipe {name}", min_value=0.0, value=1.0, step=0.25, key=f"sub_amt_{name}")
            unit = c2.selectbox(f"Unit for subrecipe {name}", UNIT_OPTIONS, index=UNIT_OPTIONS.index("portion") if "portion" in UNIT_OPTIONS else 0, key=f"sub_unit_{name}")
            recipe_items.append({"name": name, "amount": amount, "unit": unit})

        if product_items or recipe_items:
            try:
                total, allergens, components, flags = calculate_recipe(product_items, recipe_items)
                per_serving = {k: round((v or 0) / servings, 4) for k, v in total.items()}
                st.subheader("Batch Nutrition Totals")
                st.dataframe(detailed_nutrition_dataframe(total), use_container_width=True)
                st.subheader("Per-Serving Nutrition")
                st.dataframe(detailed_nutrition_dataframe(per_serving), use_container_width=True)

                st.subheader("Ingredient List Options")
                sort_pred = st.checkbox("Sort by predominance / descending weight", value=True)
                show_sub = st.checkbox("Show subrecipe ingredients in parentheses", value=True)
                emphasize = st.checkbox("Emphasize UK allergens", value=False)
                ingredient_list, list_flags = make_ingredient_list_from_components(components, show_sub, sort_pred, emphasize)
                all_flags = list(dict.fromkeys(flags + list_flags))
                st.text_area("Generated ingredient list", value=ingredient_list, height=150)
                if all_flags:
                    st.warning("Review flags:\n- " + "\n- ".join(all_flags))
                if allergens:
                    st.error("Allergens: " + ", ".join(allergens))

                if st.button("Save Recipe"):
                    recipe = {
                        "id": f"R{len(st.session_state.recipes) + 1:04d}",
                        "internal_name": clean_text(internal) or clean_text(consumer) or f"Recipe {len(st.session_state.recipes) + 1}",
                        "consumer_name": clean_text(consumer) or clean_text(internal) or f"Recipe {len(st.session_state.recipes) + 1}",
                        "name": clean_text(internal) or clean_text(consumer) or f"Recipe {len(st.session_state.recipes) + 1}",
                        "product_items": product_items,
                        "recipe_items": recipe_items,
                        "servings": servings,
                        "portion_description": portion_description,
                        "nutrition_totals": total,
                        "nutrition_per_serving": per_serving,
                        "allergens": allergens,
                        "components": components,
                        "ingredient_list": ingredient_list,
                        "review_flags": all_flags,
                        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    }
                    st.session_state.recipes.append(recipe)
                    st.success("Recipe saved.")
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        if st.session_state.recipes:
            st.subheader("Saved Recipes / Subrecipes")
            st.dataframe(recipes_dataframe(st.session_state.recipes), use_container_width=True)
            delete_choice = st.selectbox("Delete recipe", [internal_name(r) for r in st.session_state.recipes])
            if st.button("Delete Selected Recipe"):
                st.session_state.recipes = [r for r in st.session_state.recipes if internal_name(r) != delete_choice]
                st.success("Deleted.")
                st.rerun()

with tabs[5]:
    st.header("Nutrition Facts Panels")
    sources = source_options()
    if not sources:
        st.info("Add products or recipes first.")
    else:
        label = st.selectbox("Choose product or recipe", [f"{s['type']}: {s['consumer_name']} ({s['internal_name']})" for s in sources])
        source = sources[[f"{s['type']}: {s['consumer_name']} ({s['internal_name']})" for s in sources].index(label)]
        region = st.selectbox("Region", ["US", "Canada", "UK"])
        serving = st.text_input("Serving size text", value=source.get("serving", "1 serving"))
        panel = make_panel(region, source["consumer_name"], source["nutrition"], serving)
        st.text_area("Panel preview", value=panel, height=420)
        st.download_button("Download panel TXT", data=panel, file_name="nutrition_panel.txt", mime="text/plain")

with tabs[6]:
    st.header("Copy Center")
    sources = source_options()
    if not sources:
        st.info("Add products or recipes first.")
    else:
        label = st.selectbox("Choose source", [f"{s['type']}: {s['consumer_name']} ({s['internal_name']})" for s in sources], key="copy_source")
        source = sources[[f"{s['type']}: {s['consumer_name']} ({s['internal_name']})" for s in sources].index(label)]
        region = st.selectbox("Region", ["US", "Canada", "UK"], key="copy_region")
        serving = st.text_input("Serving size", value=source.get("serving", "1 serving"), key="copy_serving")
        emphasize = st.checkbox("Emphasize UK allergens in ingredient list", value=(region == "UK"), key="copy_emphasize")

        ingredient_text = source.get("ingredients_text", "Ingredients: Not available.")
        if emphasize:
            ingredient_text = emphasise_uk_allergens_in_text(ingredient_text)
        panel = make_panel(region, source["consumer_name"], source["nutrition"], serving)
        allergens = allergen_declaration(source, region)
        bundle = "\n\n".join(["=== NUTRITION PANEL ===", panel, "=== INGREDIENT LIST ===", ingredient_text, "=== ALLERGEN DECLARATION ===", allergens])
        st.text_area("Copy nutrition panel", value=panel, height=320)
        st.text_area("Copy ingredient list", value=ingredient_text, height=150)
        st.text_area("Copy allergen declaration", value=allergens, height=120)
        st.text_area("Copy all label text", value=bundle, height=520)
        st.download_button("Download copy-ready label TXT", data=bundle, file_name="copy_ready_label.txt", mime="text/plain")

with tabs[7]:
    st.header("UK PPDS / Natasha's Law Review")
    sources = source_options()
    if not sources:
        st.info("Add products or recipes first.")
    else:
        rows = []
        for s in sources:
            ingredient_text = s.get("ingredients_text", "")
            detected = detect_uk_allergens(ingredient_text)
            emphasized = emphasise_uk_allergens_in_text(ingredient_text)
            issues = []
            if not s.get("consumer_name"):
                issues.append("Missing consumer-facing food name")
            if "Not available" in ingredient_text or not ingredient_text.strip():
                issues.append("Missing full ingredients list")
            if detected and ingredient_text == emphasized:
                issues.append("Detected allergens may not be emphasized")
            rows.append({
                "Type": s["type"],
                "Internal Name": s["internal_name"],
                "Food Name": s["consumer_name"],
                "Detected UK 14 Allergens": ", ".join(detected) if detected else "None detected",
                "Generated Ingredients With Emphasis": emphasized,
                "Issues": "; ".join(issues) if issues else "None flagged by automated checklist",
                "Review Status": "Needs human compliance review",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        st.download_button("Download UK PPDS Review CSV", data=df.to_csv(index=False), file_name="uk_ppds_review.csv", mime="text/csv")

with tabs[8]:
    st.header("Export")
    if not st.session_state.products and not st.session_state.recipes:
        st.info("No data to export.")
    else:
        if st.session_state.products:
            st.download_button("Download Products CSV", data=products_dataframe(st.session_state.products).to_csv(index=False), file_name="products.csv", mime="text/csv")
        if st.session_state.recipes:
            st.download_button("Download Recipes CSV", data=recipes_dataframe(st.session_state.recipes).to_csv(index=False), file_name="recipes.csv", mime="text/csv")
        st.download_button("Download Excel Workbook", data=make_excel_export(), file_name="food_intelligence_export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
