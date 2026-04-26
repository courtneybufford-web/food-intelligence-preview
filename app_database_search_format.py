
import re
from io import BytesIO
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Food Intelligence + Recipe Labeling App", layout="wide")

COMMON_UNITS = [
    "g", "kg", "mg", "oz", "lb", "ml", "l", "tsp", "tbsp", "cup",
    "fl oz", "pint", "quart", "gallon", "each", "piece", "slice", "serving", "portion"
]

NUTRIENT_KEYS = [
    "calories", "energy_kj", "total_fat_g", "saturated_fat_g", "trans_fat_g",
    "cholesterol_mg", "sodium_mg", "total_carbs_g", "dietary_fiber_g",
    "total_sugars_g", "added_sugars_g", "protein_g", "vitamin_d_mcg",
    "calcium_mg", "iron_mg", "potassium_mg", "salt_g"
]

NUTRIENT_LABELS = {
    "calories": ("Calories", "kcal"),
    "energy_kj": ("Energy", "kJ"),
    "total_fat_g": ("Fat", "g"),
    "saturated_fat_g": ("Saturates", "g"),
    "trans_fat_g": ("Trans Fat", "g"),
    "cholesterol_mg": ("Cholesterol", "mg"),
    "sodium_mg": ("Sodium", "mg"),
    "total_carbs_g": ("Carbohydrate", "g"),
    "dietary_fiber_g": ("Fibre", "g"),
    "total_sugars_g": ("Sugars", "g"),
    "added_sugars_g": ("Added Sugars", "g"),
    "protein_g": ("Protein", "g"),
    "vitamin_d_mcg": ("Vitamin D", "mcg"),
    "calcium_mg": ("Calcium", "mg"),
    "iron_mg": ("Iron", "mg"),
    "potassium_mg": ("Potassium", "mg"),
    "salt_g": ("Salt", "g"),
}

UK_ALLERGENS = {
    "celery": ["celery"],
    "cereals containing gluten": ["wheat", "barley", "rye", "oats", "spelt", "gluten"],
    "crustaceans": ["crab", "lobster", "shrimp", "prawn", "crustacean"],
    "eggs": ["egg"],
    "fish": ["fish", "salmon", "tuna", "cod"],
    "lupin": ["lupin"],
    "milk": ["milk", "cheese", "butter", "cream", "whey", "casein", "lactose"],
    "molluscs": ["mussel", "oyster", "clam", "scallop", "mollusc"],
    "mustard": ["mustard"],
    "nuts": ["almond", "hazelnut", "walnut", "cashew", "pecan", "brazil nut", "pistachio", "macadamia"],
    "peanuts": ["peanut"],
    "sesame": ["sesame"],
    "soybeans": ["soy", "soya", "soybean"],
    "sulphur dioxide and sulphites": ["sulphite", "sulfite", "sulphur dioxide", "sulfur dioxide"],
}

SOURCE_ICONS = {"Customer Database": "👤", "USDA": "✅", "Open Food Facts": "👥"}
SOURCE_BADGES = {"Customer Database": "CUSTOMER", "USDA": "USDA", "Open Food Facts": "OFF"}

for key, default in {
    "products": [],
    "recipes": [],
    "menus": [],
    "recipe_draft_items": [],
    "formatted_search_results": [],
    "last_query": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def blank_nutrition():
    return {k: 0.0 for k in NUTRIENT_KEYS}

def safe_float(value):
    try:
        if value in [None, ""]:
            return 0.0
        return float(value)
    except Exception:
        return 0.0

def fmt(value, decimals=1):
    value = safe_float(value)
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"{value:.{decimals}f}"

def product_display_name(product):
    return product.get("consumer_name") or product.get("internal_name") or product.get("name") or "Unnamed"

def parse_nutrients(text):
    lower = text.lower()
    patterns = {
        "calories": r"\bcalories\b\D*(\d+(?:\.\d+)?)",
        "energy_kj": r"\b(?:energy|kj)\b\D*(\d+(?:\.\d+)?)",
        "total_fat_g": r"\b(?:total\s+fat|fat)\b\D*(\d+(?:\.\d+)?)",
        "saturated_fat_g": r"\b(?:saturated\s+fat|saturates)\b\D*(\d+(?:\.\d+)?)",
        "trans_fat_g": r"\btrans\s+fat\b\D*(\d+(?:\.\d+)?)",
        "cholesterol_mg": r"\bcholesterol\b\D*(\d+(?:\.\d+)?)",
        "sodium_mg": r"\bsodium\b\D*(\d+(?:\.\d+)?)",
        "total_carbs_g": r"\b(?:total\s+carbohydrate|carbohydrate|carbs)\b\D*(\d+(?:\.\d+)?)",
        "dietary_fiber_g": r"\b(?:dietary\s+fiber|fibre|fiber)\b\D*(\d+(?:\.\d+)?)",
        "total_sugars_g": r"\b(?:total\s+sugars|sugars|sugar)\b\D*(\d+(?:\.\d+)?)",
        "added_sugars_g": r"\badded\s+sugars\b\D*(\d+(?:\.\d+)?)",
        "protein_g": r"\bprotein\b\D*(\d+(?:\.\d+)?)",
        "vitamin_d_mcg": r"\bvitamin\s+d\b\D*(\d+(?:\.\d+)?)",
        "calcium_mg": r"\bcalcium\b\D*(\d+(?:\.\d+)?)",
        "iron_mg": r"\biron\b\D*(\d+(?:\.\d+)?)",
        "potassium_mg": r"\bpotassium\b\D*(\d+(?:\.\d+)?)",
        "salt_g": r"\bsalt\b\D*(\d+(?:\.\d+)?)",
    }
    nutrition = blank_nutrition()
    for key, pattern in patterns.items():
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        if match:
            nutrition[key] = safe_float(match.group(1))
    if nutrition["salt_g"] == 0 and nutrition["sodium_mg"] > 0:
        nutrition["salt_g"] = round(nutrition["sodium_mg"] * 2.5 / 1000, 3)
    if nutrition["energy_kj"] == 0 and nutrition["calories"] > 0:
        nutrition["energy_kj"] = round(nutrition["calories"] * 4.184, 1)
    return nutrition

def parse_ingredients(text):
    lower = text.lower()
    if "ingredients" not in lower:
        return []
    part = lower.split("ingredients", 1)[1]
    for stop in ["nutrition", "contains", "allergens", "allergen", "may contain", "distributed by", "manufactured by"]:
        if stop in part:
            part = part.split(stop, 1)[0]
    return [i.strip(" :.;\n\t") for i in re.split(r"[,;]", part) if i.strip(" :.;\n\t")]

def detect_allergens(text, ingredients=None):
    haystack = (text or "").lower()
    if ingredients:
        haystack += " " + " ".join(ingredients).lower()
    found = []
    for allergen, keywords in UK_ALLERGENS.items():
        if any(re.search(rf"\b{re.escape(k)}\b", haystack) for k in keywords):
            found.append(allergen)
    return sorted(set(found))

def emphasize_allergens(text):
    result = text or ""
    for _, keywords in UK_ALLERGENS.items():
        for word in keywords:
            result = re.sub(rf"\b({re.escape(word)})\b", lambda m: m.group(1).upper(), result, flags=re.IGNORECASE)
    return result

def make_product(internal_name, consumer_name, supplier, text, source="Customer Database"):
    ingredients = parse_ingredients(text)
    nutrition = parse_nutrients(text)
    allergens = detect_allergens(text, ingredients)
    return {
        "id": f"P{len(st.session_state.products) + 1:04d}",
        "internal_name": internal_name.strip(),
        "consumer_name": (consumer_name or internal_name).strip(),
        "supplier": supplier.strip(),
        "source": source,
        "ingredients": ingredients,
        "allergens": allergens,
        "nutrition": nutrition,
        "raw_text": text,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

def nutrition_add(a, b, multiplier=1.0):
    total = dict(a)
    for key in NUTRIENT_KEYS:
        total[key] = safe_float(total.get(key)) + safe_float(b.get(key)) * multiplier
    return total

def scale_nutrition(nutrition, factor):
    return {k: round(safe_float(v) * factor, 3) for k, v in nutrition.items()}

def nutrition_dataframe(nutrition):
    rows = []
    for key in NUTRIENT_KEYS:
        label, unit = NUTRIENT_LABELS[key]
        rows.append({"Nutrient": label, "Value": nutrition.get(key, 0), "Unit": unit})
    return pd.DataFrame(rows)

def products_dataframe(products):
    rows = []
    for i, p in enumerate(products):
        n = p.get("nutrition", blank_nutrition())
        rows.append({
            "ID": i,
            "Internal Name": p.get("internal_name", ""),
            "Consumer Name": product_display_name(p),
            "Supplier": p.get("supplier", ""),
            "Source": p.get("source", "Customer Database"),
            "Ingredients": ", ".join(p.get("ingredients", [])),
            "Allergens": ", ".join(p.get("allergens", [])),
            "Calories": n.get("calories", 0),
            "Fat g": n.get("total_fat_g", 0),
            "Saturates g": n.get("saturated_fat_g", 0),
            "Carbs g": n.get("total_carbs_g", 0),
            "Sugars g": n.get("total_sugars_g", 0),
            "Protein g": n.get("protein_g", 0),
            "Salt g": n.get("salt_g", 0),
            "Sodium mg": n.get("sodium_mg", 0),
        })
    return pd.DataFrame(rows)

def usda_api_key():
    try:
        return st.secrets.get("USDA_API_KEY", "")
    except Exception:
        return ""

def nutrition_from_usda(food):
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
    n = blank_nutrition()
    for item in food.get("foodNutrients", []):
        field = nutrient_map.get(item.get("nutrientName"))
        if field:
            n[field] = safe_float(item.get("value"))
    if n["salt_g"] == 0 and n["sodium_mg"] > 0:
        n["salt_g"] = round(n["sodium_mg"] * 2.5 / 1000, 3)
    if n["energy_kj"] == 0 and n["calories"] > 0:
        n["energy_kj"] = round(n["calories"] * 4.184, 1)
    return n

def search_usda(query, limit=25):
    key = usda_api_key()
    if not key or not query:
        return []
    try:
        response = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={"api_key": key, "query": query, "pageSize": limit},
            timeout=15,
        )
        response.raise_for_status()
        out = []
        for food in response.json().get("foods", []):
            name = (food.get("description") or "USDA Food").title()
            out.append({
                "source": "USDA",
                "name": name,
                "supplier": "USDA FoodData Central",
                "ingredients": [name.lower()],
                "allergens": detect_allergens(name),
                "nutrition": nutrition_from_usda(food),
                "raw_text": str(food),
            })
        return out
    except Exception as exc:
        st.warning(f"USDA search failed: {exc}")
        return []

def nutrition_from_off(item):
    nutriments = item.get("nutriments", {}) or {}
    def n(*keys):
        for key in keys:
            if nutriments.get(key) not in [None, ""]:
                return safe_float(nutriments.get(key))
        return 0.0
    out = blank_nutrition()
    out["calories"] = n("energy-kcal_100g", "energy-kcal_serving")
    out["energy_kj"] = n("energy-kj_100g", "energy-kj_serving") or round(out["calories"] * 4.184, 1)
    out["total_fat_g"] = n("fat_100g", "fat_serving")
    out["saturated_fat_g"] = n("saturated-fat_100g", "saturated-fat_serving")
    out["trans_fat_g"] = n("trans-fat_100g", "trans-fat_serving")
    out["cholesterol_mg"] = n("cholesterol_100g", "cholesterol_serving")
    out["sodium_mg"] = n("sodium_100g", "sodium_serving") * 1000
    out["total_carbs_g"] = n("carbohydrates_100g", "carbohydrates_serving")
    out["dietary_fiber_g"] = n("fiber_100g", "fiber_serving")
    out["total_sugars_g"] = n("sugars_100g", "sugars_serving")
    out["protein_g"] = n("proteins_100g", "proteins_serving")
    out["salt_g"] = n("salt_100g", "salt_serving") or round(out["sodium_mg"] * 2.5 / 1000, 3)
    return out

def search_open_food_facts(query, limit=25):
    if not query:
        return []
    try:
        response = requests.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": query,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": limit,
                "fields": "product_name,generic_name,brands,ingredients_text,nutriments",
            },
            headers={"User-Agent": "FoodIntelligencePreview/1.0"},
            timeout=15,
        )
        response.raise_for_status()
        out = []
        for item in response.json().get("products", []):
            name = item.get("product_name") or item.get("generic_name") or "Unnamed Open Food Facts Product"
            ingredients_text = item.get("ingredients_text", "") or ""
            ingredients = [x.strip() for x in ingredients_text.split(",") if x.strip()]
            out.append({
                "source": "Open Food Facts",
                "name": name,
                "supplier": item.get("brands", ""),
                "ingredients": ingredients,
                "allergens": detect_allergens(ingredients_text, ingredients),
                "nutrition": nutrition_from_off(item),
                "raw_text": ingredients_text,
            })
        return out
    except Exception as exc:
        st.warning(f"Open Food Facts search failed: {exc}")
        return []

def combined_database_search(query, limit=25):
    results = []
    q = query.lower().strip()
    for p in st.session_state.products:
        searchable = " ".join([
            p.get("internal_name", ""), product_display_name(p), p.get("supplier", ""),
            " ".join(p.get("ingredients", [])), " ".join(p.get("allergens", [])),
        ]).lower()
        if q in searchable:
            results.append({
                "source": "Customer Database",
                "name": product_display_name(p),
                "supplier": p.get("supplier", ""),
                "ingredients": p.get("ingredients", []),
                "allergens": p.get("allergens", []),
                "nutrition": p.get("nutrition", blank_nutrition()),
                "raw_text": p.get("raw_text", ""),
            })
    results.extend(search_usda(query, limit))
    results.extend(search_open_food_facts(query, limit))
    return results

def result_to_product(result):
    return {
        "id": f"P{len(st.session_state.products) + 1:04d}",
        "internal_name": result["name"],
        "consumer_name": result["name"],
        "supplier": result.get("supplier") or result.get("source", ""),
        "source": result.get("source", "Imported"),
        "ingredients": result.get("ingredients", []),
        "allergens": result.get("allergens", []),
        "nutrition": result.get("nutrition", blank_nutrition()),
        "raw_text": result.get("raw_text", ""),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

def add_result_to_recipe(result, default_amount=1.0, default_unit="serving"):
    product = result_to_product(result)
    st.session_state.products.append(product)
    st.session_state.recipe_draft_items.append({
        "product_name": product_display_name(product),
        "amount": default_amount,
        "unit": default_unit,
    })

def find_product_by_name(name):
    return next((p for p in st.session_state.products if product_display_name(p) == name), None)

def recipe_totals(items):
    total = blank_nutrition()
    allergens = set()
    ingredient_parts = []
    rows = []
    for item in items:
        p = find_product_by_name(item["product_name"])
        if not p:
            continue
        amount = safe_float(item.get("amount", 1))
        total = nutrition_add(total, p.get("nutrition", blank_nutrition()), amount)
        allergens.update(p.get("allergens", []))
        name = product_display_name(p)
        ingredient_parts.append((amount, name))
        rows.append({"Ingredient/Product": name, "Amount": amount, "Unit": item.get("unit", "serving")})
    ingredient_parts.sort(key=lambda x: x[0], reverse=True)
    ingredient_list = ", ".join([x[1] for x in ingredient_parts])
    return total, sorted(allergens), emphasize_allergens(ingredient_list), rows

def label_text(country, food_name, nutrition, ingredient_list, allergens, servings=1):
    per = scale_nutrition(nutrition, 1 / max(safe_float(servings), 1))
    allergen_line = "Contains: " + ", ".join(allergens) if allergens else "No declarable allergens detected by automated review."
    if country == "UK / Natasha's Law":
        return f"""{food_name}

Ingredients: {ingredient_list}

{allergen_line}

Nutrition Declaration — Typical values per serving
Energy: {fmt(per.get('energy_kj'))} kJ / {fmt(per.get('calories'))} kcal
Fat: {fmt(per.get('total_fat_g'))} g
of which saturates: {fmt(per.get('saturated_fat_g'))} g
Carbohydrate: {fmt(per.get('total_carbs_g'))} g
of which sugars: {fmt(per.get('total_sugars_g'))} g
Protein: {fmt(per.get('protein_g'))} g
Salt: {fmt(per.get('salt_g'), 2)} g

PPDS / Natasha's Law review aid: confirm food name, complete ingredients list, allergen emphasis, and final label before sale."""
    if country == "US":
        return f"""Nutrition Facts — Draft
Food: {food_name}
Servings: {fmt(servings)}
Calories {fmt(per.get('calories'))}
Total Fat {fmt(per.get('total_fat_g'))}g
Saturated Fat {fmt(per.get('saturated_fat_g'))}g
Trans Fat {fmt(per.get('trans_fat_g'))}g
Cholesterol {fmt(per.get('cholesterol_mg'))}mg
Sodium {fmt(per.get('sodium_mg'))}mg
Total Carbohydrate {fmt(per.get('total_carbs_g'))}g
Dietary Fiber {fmt(per.get('dietary_fiber_g'))}g
Total Sugars {fmt(per.get('total_sugars_g'))}g
Added Sugars {fmt(per.get('added_sugars_g'))}g
Protein {fmt(per.get('protein_g'))}g
Vitamin D {fmt(per.get('vitamin_d_mcg'))}mcg
Calcium {fmt(per.get('calcium_mg'))}mg
Iron {fmt(per.get('iron_mg'))}mg
Potassium {fmt(per.get('potassium_mg'))}mg

Ingredients: {ingredient_list}
{allergen_line}"""
    return f"""Canadian Nutrition Facts — Draft
Food: {food_name}
Servings: {fmt(servings)}
Calories {fmt(per.get('calories'))}
Fat {fmt(per.get('total_fat_g'))}g
Saturated Fat {fmt(per.get('saturated_fat_g'))}g
Carbohydrate {fmt(per.get('total_carbs_g'))}g
Fibre {fmt(per.get('dietary_fiber_g'))}g
Sugars {fmt(per.get('total_sugars_g'))}g
Protein {fmt(per.get('protein_g'))}g
Cholesterol {fmt(per.get('cholesterol_mg'))}mg
Sodium {fmt(per.get('sodium_mg'))}mg
Potassium {fmt(per.get('potassium_mg'))}mg
Calcium {fmt(per.get('calcium_mg'))}mg
Iron {fmt(per.get('iron_mg'))}mg

Ingredients: {ingredient_list}
{allergen_line}"""

def export_recipe_excel(recipe, country):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        nutrition_dataframe(recipe["nutrition_per_serving"]).to_excel(writer, sheet_name="Nutrition_Per_Serving", index=False)
        pd.DataFrame(recipe["items"]).to_excel(writer, sheet_name="Recipe_Items", index=False)
        pd.DataFrame([{
            "Country/Profile": country,
            "Food Name": recipe["consumer_name"],
            "Servings": recipe["servings"],
            "Ingredients": recipe["ingredient_list"],
            "Allergens": ", ".join(recipe["allergens"]),
            "Label Text": recipe["label_text"],
        }]).to_excel(writer, sheet_name="Label", index=False)
    return output.getvalue()

def export_label_pdf(label):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    width, height = letter
    y = height - inch
    c.setFont("Helvetica", 10)
    for raw_line in label.split("\n"):
        line = raw_line[:110]
        c.drawString(inch, y, line)
        y -= 14
        if y < inch:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - inch
    c.save()
    return output.getvalue()

def result_subtitle(result):
    n = result.get("nutrition", blank_nutrition())
    bits = []
    if n.get("calories"):
        bits.append(f"{fmt(n.get('calories'))} cal")
    if n.get("protein_g"):
        bits.append(f"{fmt(n.get('protein_g'))}g protein")
    if n.get("sodium_mg"):
        bits.append(f"{fmt(n.get('sodium_mg'))}mg sodium")
    if not bits:
        bits.append("nutrition available after preview/import")
    return " • ".join(bits)

def render_search_results(results, context="recipe"):
    if not results:
        st.info("No results found yet.")
        return
    for idx, result in enumerate(results):
        source = result.get("source", "Database")
        icon = SOURCE_ICONS.get(source, "🔎")
        badge = SOURCE_BADGES.get(source, source.upper())
        name = result.get("name", "Unnamed")
        supplier = result.get("supplier", "")
        subtitle = result_subtitle(result)
        with st.container(border=True):
            c_icon, c_text, c_add, c_preview = st.columns([0.4, 5, 1.4, 1.2], vertical_alignment="center")
            with c_icon:
                st.markdown(f"### {icon}")
            with c_text:
                st.markdown(f"**{name}**  ` {badge} `")
                small = subtitle
                if supplier:
                    small += f"  |  {supplier}"
                st.caption(small)
                if result.get("allergens"):
                    st.warning("Allergens: " + ", ".join(result.get("allergens", [])))
            with c_add:
                if st.button("+ Add to Recipe", key=f"add_{context}_{idx}_{name}"):
                    add_result_to_recipe(result)
                    st.success(f"Added {name} to recipe draft.")
                    st.rerun()
            with c_preview:
                with st.expander("Preview"):
                    st.write("**Ingredients**")
                    st.write(", ".join(result.get("ingredients", [])) or "Not available")
                    st.write("**Nutrition**")
                    st.dataframe(nutrition_dataframe(result.get("nutrition", blank_nutrition())), use_container_width=True, hide_index=True)

st.title("Food Intelligence + Recipe Labeling App")

with st.sidebar:
    st.header("Demo Controls")
    if st.button("Load Demo Products"):
        demo = [
            ("Chicken Roti-Bulk", "Chicken Roti-Bulk", "Customer", "Ingredients: chicken, wheat wrap, yogurt, spices\nNutrition: Calories 37274 Protein 900g Fat 800g Carbs 4500g Sodium 12000mg"),
            ("Harissa Chicken-Bulk", "Harissa Chicken-Bulk", "Customer", "Ingredients: chicken, harissa paste, garlic, oil\nNutrition: Calories 4372 Protein 250g Fat 180g Carbs 120g Sodium 3200mg"),
            ("Pacific Organic Low Sodium Chicken Broth", "Pacific Organic Low Sodium Chicken Broth", "Pacific", "Ingredients: chicken broth, sea salt\nNutrition: Calories 10 Protein 1g Fat 0g Carbs 1g Sodium 70mg"),
        ]
        for d in demo:
            st.session_state.products.append(make_product(*d))
        st.success("Demo products loaded.")
        st.rerun()
    if st.button("Clear All"):
        st.session_state.products = []
        st.session_state.recipes = []
        st.session_state.menus = []
        st.session_state.recipe_draft_items = []
        st.session_state.formatted_search_results = []
        st.rerun()

tabs = st.tabs(["Dashboard", "Add Product", "Recipe Builder", "Create Menu", "Export"])

with tabs[0]:
    st.header("Dashboard")
    c1, c2, c3 = st.columns(3)
    c1.metric("Products / Ingredients", len(st.session_state.products))
    c2.metric("Recipes", len(st.session_state.recipes))
    c3.metric("Menus", len(st.session_state.menus))
    if st.session_state.products:
        st.dataframe(products_dataframe(st.session_state.products), use_container_width=True)
    else:
        st.info("No products yet. Add products manually, search databases in Recipe Builder, or load demo products.")

with tabs[1]:
    st.header("Add Product / Ingredient")
    internal = st.text_input("Internal Name", placeholder="Internal SKU or prep name")
    consumer = st.text_input("Consumer-Facing Name", placeholder="Name shown on labels")
    supplier = st.text_input("Supplier")
    default_text = "Ingredients: wheat flour, sugar, salt, soy lecithin\nNutrition: Calories 120 Total Fat 2g Saturated Fat 1g Total Carbohydrate 24g Sugars 5g Protein 4g Sodium 200mg"
    text = st.text_area("Paste product specification text", default_text, height=220)
    if st.button("Parse and Save Product"):
        if not internal.strip():
            st.warning("Internal name is required.")
        else:
            st.session_state.products.append(make_product(internal, consumer or internal, supplier, text))
            st.success("Product saved.")
            st.rerun()

with tabs[2]:
    st.header("Recipe Builder")

    st.subheader("Search ingredients, products, and databases")
    st.caption("Results are shown in an add-to-recipe format similar to commercial recipe systems.")
    q_col, l_col = st.columns([4, 1])
    query = q_col.text_input("Search", placeholder="chicken, flour, milk, broth...", label_visibility="collapsed")
    result_limit = l_col.selectbox("Results", [10, 25, 50], index=1)

    if query and len(query.strip()) >= 2:
        if query != st.session_state.last_query:
            st.session_state.formatted_search_results = combined_database_search(query, result_limit)
            st.session_state.last_query = query
        render_search_results(st.session_state.formatted_search_results, context="live")
    elif query:
        st.caption("Type at least 2 characters to preview results.")

    st.divider()
    st.subheader("Current Recipe Draft")
    if not st.session_state.recipe_draft_items:
        st.info("Use + Add to Recipe from the search results, or select saved customer products below.")
    else:
        edited_items = []
        for idx, item in enumerate(st.session_state.recipe_draft_items):
            c1, c2, c3, c4 = st.columns([3, 1, 1.2, 0.8], vertical_alignment="center")
            c1.write(item["product_name"])
            amount = c2.number_input("Amount", min_value=0.0, value=safe_float(item.get("amount", 1)), step=0.25, key=f"draft_amt_{idx}")
            unit = c3.selectbox("Unit", COMMON_UNITS, index=COMMON_UNITS.index(item.get("unit", "serving")) if item.get("unit", "serving") in COMMON_UNITS else 0, key=f"draft_unit_{idx}")
            remove = c4.button("Remove", key=f"remove_draft_{idx}")
            if not remove:
                edited_items.append({"product_name": item["product_name"], "amount": amount, "unit": unit})
        st.session_state.recipe_draft_items = edited_items

    if st.session_state.products:
        with st.expander("Add saved customer products manually"):
            selected = st.multiselect("Saved customer products", [product_display_name(p) for p in st.session_state.products])
            if st.button("Add selected saved products to recipe"):
                for name in selected:
                    st.session_state.recipe_draft_items.append({"product_name": name, "amount": 1.0, "unit": "serving"})
                st.rerun()

    if st.session_state.recipe_draft_items:
        total, allergens, ingredient_list, item_rows = recipe_totals(st.session_state.recipe_draft_items)
        st.subheader("Recipe Items")
        st.dataframe(pd.DataFrame(item_rows), use_container_width=True, hide_index=True)
        c1, c2, c3 = st.columns(3)
        recipe_internal = c1.text_input("Recipe Internal Name")
        recipe_consumer = c2.text_input("Recipe Consumer-Facing Name")
        servings = c3.number_input("Number of servings", min_value=1.0, value=1.0, step=0.5)
        per_serving = scale_nutrition(total, 1 / max(servings, 1))

        st.subheader("Nutrition Per Serving")
        st.dataframe(nutrition_dataframe(per_serving), use_container_width=True, hide_index=True)
        if allergens:
            st.error("Allergen warning: " + ", ".join(allergens))
        else:
            st.success("No declarable allergens detected by automated review.")

        if st.button("Save Recipe"):
            if not recipe_internal.strip():
                st.warning("Recipe internal name is required.")
            else:
                recipe = {
                    "internal_name": recipe_internal,
                    "consumer_name": recipe_consumer or recipe_internal,
                    "servings": servings,
                    "items": item_rows,
                    "draft_items": st.session_state.recipe_draft_items.copy(),
                    "nutrition_totals": total,
                    "nutrition_per_serving": per_serving,
                    "ingredient_list": ingredient_list,
                    "allergens": allergens,
                    "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                }
                st.session_state.recipes.append(recipe)
                st.session_state.recipe_draft_items = []
                st.success("Recipe saved.")
                st.rerun()

    if st.session_state.recipes:
        st.divider()
        st.subheader("Saved Recipes + Label Preview")
        selected_recipe_name = st.selectbox("Select saved recipe", [r["consumer_name"] for r in st.session_state.recipes])
        recipe = next(r for r in st.session_state.recipes if r["consumer_name"] == selected_recipe_name)
        country = st.selectbox("Country / label profile", ["UK / Natasha's Law", "US", "Canada"])
        label = label_text(country, recipe["consumer_name"], recipe["nutrition_totals"], recipe["ingredient_list"], recipe["allergens"], recipe["servings"])
        recipe["label_text"] = label
        st.text_area("Label Preview", label, height=420)
        c1, c2, c3 = st.columns(3)
        c1.download_button("Download Label TXT", data=label, file_name=f"{recipe['consumer_name']}_label.txt", mime="text/plain")
        c2.download_button("Download Label PDF", data=export_label_pdf(label), file_name=f"{recipe['consumer_name']}_label.pdf", mime="application/pdf")
        c3.download_button("Download Excel", data=export_recipe_excel(recipe, country), file_name=f"{recipe['consumer_name']}_label.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tabs[3]:
    st.header("Create Menu")
    if not st.session_state.recipes:
        st.info("Save recipes first.")
    else:
        menu_name = st.text_input("Menu Name")
        category = st.text_input("Menu Category", placeholder="Breakfast, Entrees, Desserts, Specials")
        selected_recipes = st.multiselect("Select recipes for this menu/category", [r["consumer_name"] for r in st.session_state.recipes])
        if st.button("Save Menu Category"):
            if not menu_name or not category:
                st.warning("Menu name and category are required.")
            else:
                st.session_state.menus.append({"name": menu_name, "category": category, "recipes": selected_recipes})
                st.success("Menu category saved.")
                st.rerun()
        for menu in st.session_state.menus:
            with st.expander(f"{menu['name']} — {menu['category']}"):
                st.write(menu["recipes"])

with tabs[4]:
    st.header("Export")
    if st.session_state.products:
        st.download_button("Download Product Database CSV", data=products_dataframe(st.session_state.products).to_csv(index=False), file_name="products.csv", mime="text/csv")
    if st.session_state.recipes:
        all_rows = []
        for r in st.session_state.recipes:
            row = {
                "Internal Name": r["internal_name"],
                "Consumer Name": r["consumer_name"],
                "Servings": r["servings"],
                "Ingredients": r["ingredient_list"],
                "Allergens": ", ".join(r["allergens"]),
            }
            row.update({f"per_serving_{k}": v for k, v in r["nutrition_per_serving"].items()})
            all_rows.append(row)
        st.download_button("Download Recipe Database CSV", data=pd.DataFrame(all_rows).to_csv(index=False), file_name="recipes.csv", mime="text/csv")

st.caption("Compliance note: label outputs are review aids and should be checked by a qualified food labeling/compliance professional before commercial use.")
