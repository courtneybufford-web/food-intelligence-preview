import re
import requests
import pandas as pd
import streamlit as st
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Food Intelligence App", layout="wide")

COMMON_UNITS = [
    "g", "kg", "mg", "oz", "lb",
    "ml", "l", "tsp", "tbsp", "cup",
    "fl oz", "pint", "quart", "gallon",
    "each", "piece", "slice", "serving", "portion"
]

NUTRIENT_KEYS = [
    "calories", "energy_kj", "total_fat_g", "saturated_fat_g",
    "trans_fat_g", "cholesterol_mg", "sodium_mg",
    "total_carbs_g", "dietary_fiber_g", "total_sugars_g",
    "added_sugars_g", "protein_g", "vitamin_d_mcg",
    "calcium_mg", "iron_mg", "potassium_mg", "salt_g"
]

COUNTRIES = ["UK / Natasha's Law", "US", "Canada"]

UK_ALLERGENS = {
    "celery": ["celery"],
    "cereals containing gluten": ["wheat", "barley", "rye", "oats", "spelt", "gluten"],
    "crustaceans": ["crab", "lobster", "shrimp", "prawn", "crustacean"],
    "eggs": ["egg"],
    "fish": ["fish"],
    "lupin": ["lupin"],
    "milk": ["milk", "cheese", "butter", "cream", "whey", "casein", "lactose"],
    "molluscs": ["mussel", "oyster", "clam", "scallop", "mollusc"],
    "mustard": ["mustard"],
    "nuts": ["almond", "hazelnut", "walnut", "cashew", "pecan", "brazil nut", "pistachio", "macadamia"],
    "peanuts": ["peanut"],
    "sesame": ["sesame"],
    "soybeans": ["soy", "soya", "soybean"],
    "sulphur dioxide and sulphites": ["sulphite", "sulfite", "sulphur dioxide", "sulfur dioxide"]
}

US_COMMON_ALLERGENS = {
    "milk": ["milk", "cheese", "butter", "cream", "whey", "casein", "lactose"],
    "eggs": ["egg"],
    "fish": ["fish"],
    "crustacean shellfish": ["crab", "lobster", "shrimp", "prawn", "crustacean", "shellfish"],
    "tree nuts": ["almond", "hazelnut", "walnut", "cashew", "pecan", "brazil nut", "pistachio", "macadamia"],
    "peanuts": ["peanut"],
    "wheat": ["wheat"],
    "soybeans": ["soy", "soya", "soybean"],
    "sesame": ["sesame"],
}

CANADA_PRIORITY_ALLERGENS = {
    **US_COMMON_ALLERGENS,
    "mustard": ["mustard"],
    "sulphites": ["sulphite", "sulfite", "sulphur dioxide", "sulfur dioxide"],
}

if "products" not in st.session_state:
    st.session_state.products = []
if "recipes" not in st.session_state:
    st.session_state.recipes = []
if "menus" not in st.session_state:
    st.session_state.menus = []
if "search_results" not in st.session_state:
    st.session_state.search_results = []


def blank_nutrition():
    return {k: 0.0 for k in NUTRIENT_KEYS}


def safe_float(value):
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def fmt(value, decimals=1):
    value = safe_float(value)
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"{value:.{decimals}f}"


def parse_nutrients(text):
    lower = text.lower()
    patterns = {
        "calories": r"calories\D*(\d+\.?\d*)",
        "energy_kj": r"(?:energy|kj)\D*(\d+\.?\d*)",
        "total_fat_g": r"(?:total fat|fat)\D*(\d+\.?\d*)",
        "saturated_fat_g": r"(?:saturated fat|saturates)\D*(\d+\.?\d*)",
        "trans_fat_g": r"trans fat\D*(\d+\.?\d*)",
        "cholesterol_mg": r"cholesterol\D*(\d+\.?\d*)",
        "sodium_mg": r"sodium\D*(\d+\.?\d*)",
        "total_carbs_g": r"(?:total carbohydrate|carbohydrate|carbs)\D*(\d+\.?\d*)",
        "dietary_fiber_g": r"(?:dietary fiber|fibre|fiber)\D*(\d+\.?\d*)",
        "total_sugars_g": r"(?:total sugars|sugars|sugar)\D*(\d+\.?\d*)",
        "added_sugars_g": r"added sugars\D*(\d+\.?\d*)",
        "protein_g": r"protein\D*(\d+\.?\d*)",
        "vitamin_d_mcg": r"vitamin d\D*(\d+\.?\d*)",
        "calcium_mg": r"calcium\D*(\d+\.?\d*)",
        "iron_mg": r"iron\D*(\d+\.?\d*)",
        "potassium_mg": r"potassium\D*(\d+\.?\d*)",
        "salt_g": r"salt\D*(\d+\.?\d*)",
    }
    nutrition = blank_nutrition()
    for key, pattern in patterns.items():
        match = re.search(pattern, lower)
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
    for stop in ["nutrition", "allergen", "contains"]:
        if stop in part:
            part = part.split(stop, 1)[0]
    return [i.strip(" :.\n") for i in part.split(",") if i.strip(" :.\n")]


def detect_allergens(text, ingredients=None, country="UK / Natasha's Law"):
    haystack = text.lower()
    if ingredients:
        haystack += " " + " ".join(ingredients).lower()
    allergen_map = UK_ALLERGENS if country.startswith("UK") else US_COMMON_ALLERGENS if country == "US" else CANADA_PRIORITY_ALLERGENS
    found = []
    for allergen, keywords in allergen_map.items():
        if any(re.search(rf"\b{re.escape(k)}\b", haystack) for k in keywords):
            found.append(allergen)
    return sorted(set(found))


def product_dataframe(products):
    rows = []
    for idx, p in enumerate(products):
        n = p["nutrition"]
        rows.append({
            "ID": idx,
            "Internal Name": p.get("internal_name", ""),
            "Consumer Name": p.get("consumer_name", ""),
            "Supplier": p.get("supplier", ""),
            "Source": p.get("source", "customer"),
            "Ingredients": ", ".join(p.get("ingredients", [])),
            "Allergens": ", ".join(p.get("allergens", [])),
            "Calories": n.get("calories", 0),
            "Energy kJ": n.get("energy_kj", 0),
            "Fat g": n.get("total_fat_g", 0),
            "Saturates g": n.get("saturated_fat_g", 0),
            "Carbs g": n.get("total_carbs_g", 0),
            "Sugars g": n.get("total_sugars_g", 0),
            "Protein g": n.get("protein_g", 0),
            "Salt g": n.get("salt_g", 0),
            "Sodium mg": n.get("sodium_mg", 0),
        })
    return pd.DataFrame(rows)


def make_product(internal_name, consumer_name, supplier, text, source="customer"):
    ingredients = parse_ingredients(text)
    nutrition = parse_nutrients(text)
    allergens = detect_allergens(text, ingredients)
    return {
        "internal_name": internal_name,
        "consumer_name": consumer_name or internal_name,
        "supplier": supplier,
        "ingredients": ingredients,
        "allergens": allergens,
        "nutrition": nutrition,
        "raw_text": text,
        "source": source
    }


def nutrition_from_off(product):
    nutriments = product.get("nutriments", {})
    n = blank_nutrition()
    n["calories"] = safe_float(nutriments.get("energy-kcal_100g"))
    n["energy_kj"] = safe_float(nutriments.get("energy-kj_100g")) or round(n["calories"] * 4.184, 1)
    n["total_fat_g"] = safe_float(nutriments.get("fat_100g"))
    n["saturated_fat_g"] = safe_float(nutriments.get("saturated-fat_100g"))
    n["total_carbs_g"] = safe_float(nutriments.get("carbohydrates_100g"))
    n["total_sugars_g"] = safe_float(nutriments.get("sugars_100g"))
    n["dietary_fiber_g"] = safe_float(nutriments.get("fiber_100g"))
    n["protein_g"] = safe_float(nutriments.get("proteins_100g"))
    n["salt_g"] = safe_float(nutriments.get("salt_100g"))
    n["sodium_mg"] = safe_float(nutriments.get("sodium_100g")) * 1000
    return n


def search_open_food_facts(query, limit=25):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {"search_terms": query, "search_simple": 1, "action": "process", "json": 1, "page_size": limit}
    try:
        data = requests.get(url, params=params, timeout=10).json()
        results = []
        for item in data.get("products", []):
            name = item.get("product_name") or item.get("generic_name") or "Unnamed OFF Product"
            ingredients_text = item.get("ingredients_text", "")
            ingredients = [x.strip() for x in ingredients_text.split(",") if x.strip()]
            nutrition = nutrition_from_off(item)
            allergens = detect_allergens(ingredients_text, ingredients)
            results.append({
                "source": "Open Food Facts",
                "name": name,
                "supplier": item.get("brands", ""),
                "ingredients": ingredients,
                "allergens": allergens,
                "nutrition": nutrition,
                "raw_text": ingredients_text
            })
        return results
    except Exception as e:
        st.warning(f"Open Food Facts search failed: {e}")
        return []


def search_usda(query, limit=25):
    api_key = st.secrets.get("USDA_API_KEY", "")
    if not api_key:
        return []
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {"query": query, "pageSize": limit, "api_key": api_key}
    try:
        data = requests.get(url, params=params, timeout=10).json()
        results = []
        for food in data.get("foods", []):
            n = blank_nutrition()
            for nutrient in food.get("foodNutrients", []):
                name = nutrient.get("nutrientName", "").lower()
                value = safe_float(nutrient.get("value"))
                unit = nutrient.get("unitName", "").lower()
                if "energy" in name and "kcal" in unit:
                    n["calories"] = value
                elif "energy" in name and "kj" in unit:
                    n["energy_kj"] = value
                elif name == "protein":
                    n["protein_g"] = value
                elif name in ["total lipid (fat)", "total fat"]:
                    n["total_fat_g"] = value
                elif "saturated" in name:
                    n["saturated_fat_g"] = value
                elif "carbohydrate" in name:
                    n["total_carbs_g"] = value
                elif "fiber" in name:
                    n["dietary_fiber_g"] = value
                elif "sugars" in name:
                    n["total_sugars_g"] = value
                elif name == "sodium, na":
                    n["sodium_mg"] = value
                    n["salt_g"] = round(value * 2.5 / 1000, 3)
                elif name == "calcium, ca":
                    n["calcium_mg"] = value
                elif name == "iron, fe":
                    n["iron_mg"] = value
                elif name == "potassium, k":
                    n["potassium_mg"] = value
            if n["energy_kj"] == 0 and n["calories"] > 0:
                n["energy_kj"] = round(n["calories"] * 4.184, 1)
            desc = food.get("description", "USDA Food")
            results.append({
                "source": "USDA",
                "name": desc.title(),
                "supplier": "USDA FoodData Central",
                "ingredients": [desc.lower()],
                "allergens": detect_allergens(desc),
                "nutrition": n,
                "raw_text": desc
            })
        return results
    except Exception as e:
        st.warning(f"USDA search failed: {e}")
        return []


def combined_search(query):
    results = []
    for p in st.session_state.products:
        searchable = " ".join([p.get("internal_name", ""), p.get("consumer_name", ""), p.get("supplier", ""), " ".join(p.get("ingredients", [])), " ".join(p.get("allergens", []))]).lower()
        if query.lower() in searchable:
            results.append({
                "source": "Customer Database",
                "name": p.get("consumer_name", p.get("internal_name", "")),
                "supplier": p.get("supplier", ""),
                "ingredients": p.get("ingredients", []),
                "allergens": p.get("allergens", []),
                "nutrition": p.get("nutrition", blank_nutrition()),
                "raw_text": p.get("raw_text", "")
            })
    results.extend(search_usda(query, 25))
    results.extend(search_open_food_facts(query, 25))
    return results


def nutrition_add(a, b, multiplier=1.0):
    total = dict(a)
    for key in NUTRIENT_KEYS:
        total[key] = safe_float(total.get(key)) + safe_float(b.get(key)) * multiplier
    return total


def scale_nutrition(nutrition, factor):
    return {k: round(safe_float(v) * factor, 3) for k, v in nutrition.items()}


def recipe_total(recipe, seen=None):
    if seen is None:
        seen = set()
    if recipe["name"] in seen:
        return blank_nutrition(), {"CIRCULAR RECIPE WARNING"}
    seen.add(recipe["name"])
    total = blank_nutrition()
    allergens = set()
    for item in recipe.get("items", []):
        if item["type"] == "product":
            p = next((x for x in st.session_state.products if x["consumer_name"] == item["name"]), None)
            if p:
                total = nutrition_add(total, p["nutrition"], item["amount"])
                allergens.update(p["allergens"])
        elif item["type"] == "recipe":
            r = next((x for x in st.session_state.recipes if x["name"] == item["name"]), None)
            if r:
                sub_total, sub_allergens = recipe_total(r, seen)
                total = nutrition_add(total, sub_total, item["amount"])
                allergens.update(sub_allergens)
    return total, allergens


def emphasize_allergens(text, country="UK / Natasha's Law"):
    allergen_map = UK_ALLERGENS if country.startswith("UK") else US_COMMON_ALLERGENS if country == "US" else CANADA_PRIORITY_ALLERGENS
    result = text
    for keywords in allergen_map.values():
        for word in keywords:
            result = re.sub(rf"\b({re.escape(word)})\b", lambda m: m.group(1).upper(), result, flags=re.IGNORECASE)
    return result


def build_ingredient_list_for_recipe(recipe, parenthesize_subrecipes=True, emphasize=True, country="UK / Natasha's Law"):
    parts = []
    for item in recipe.get("items", []):
        if item["type"] == "product":
            p = next((x for x in st.session_state.products if x["consumer_name"] == item["name"]), None)
            if p:
                parts.append((item["amount"], p.get("consumer_name", item["name"])))
        elif item["type"] == "recipe":
            r = next((x for x in st.session_state.recipes if x["name"] == item["name"]), None)
            if r:
                if parenthesize_subrecipes:
                    sub_parts = build_ingredient_list_for_recipe(r, True, False, country)
                    display = f"{r['consumer_name']} ({sub_parts})"
                else:
                    display = r["consumer_name"]
                parts.append((item["amount"], display))
    parts.sort(key=lambda x: x[0], reverse=True)
    text = ", ".join([p[1] for p in parts])
    return emphasize_allergens(text, country) if emphasize else text


def allergen_declaration(allergens, country):
    if not allergens:
        return "No declarable allergens detected. Review required."
    prefix = "Contains" if country in ["US", "Canada"] else "Allergens"
    return f"{prefix}: " + ", ".join(sorted(allergens))


def label_text(recipe, country):
    total, allergens = recipe_total(recipe)
    servings = max(recipe.get("servings", 1), 1)
    per_serving = scale_nutrition(total, 1 / servings)
    ingredient_list = build_ingredient_list_for_recipe(recipe, True, True, country)
    allergen_text = allergen_declaration(allergens, country)
    food_name = recipe["consumer_name"]

    if country.startswith("UK"):
        panel = f"""{food_name}

Ingredients: {ingredient_list}

{allergen_text}

Nutrition Declaration - Typical values per serving
Energy: {fmt(per_serving.get('energy_kj'))} kJ / {fmt(per_serving.get('calories'))} kcal
Fat: {fmt(per_serving.get('total_fat_g'))} g
of which saturates: {fmt(per_serving.get('saturated_fat_g'))} g
Carbohydrate: {fmt(per_serving.get('total_carbs_g'))} g
of which sugars: {fmt(per_serving.get('total_sugars_g'))} g
Protein: {fmt(per_serving.get('protein_g'))} g
Salt: {fmt(per_serving.get('salt_g'), 2)} g

UK PPDS / Natasha's Law review checklist:
[ ] Food name confirmed
[ ] Full ingredients list confirmed
[ ] 14 UK allergens emphasized in ingredients list
[ ] Descending order by weight verified
[ ] Human compliance review completed
"""
    elif country == "US":
        panel = f"""{food_name}

Ingredients: {ingredient_list}

{allergen_text}

Nutrition Facts - Draft Review
Servings per recipe: {servings}
Amount per serving
Calories {fmt(per_serving.get('calories'))}
Total Fat {fmt(per_serving.get('total_fat_g'))}g
Saturated Fat {fmt(per_serving.get('saturated_fat_g'))}g
Trans Fat {fmt(per_serving.get('trans_fat_g'))}g
Cholesterol {fmt(per_serving.get('cholesterol_mg'))}mg
Sodium {fmt(per_serving.get('sodium_mg'))}mg
Total Carbohydrate {fmt(per_serving.get('total_carbs_g'))}g
Dietary Fiber {fmt(per_serving.get('dietary_fiber_g'))}g
Total Sugars {fmt(per_serving.get('total_sugars_g'))}g
Includes Added Sugars {fmt(per_serving.get('added_sugars_g'))}g
Protein {fmt(per_serving.get('protein_g'))}g
Vitamin D {fmt(per_serving.get('vitamin_d_mcg'))}mcg
Calcium {fmt(per_serving.get('calcium_mg'))}mg
Iron {fmt(per_serving.get('iron_mg'))}mg
Potassium {fmt(per_serving.get('potassium_mg'))}mg

US label review checklist:
[ ] Serving size verified
[ ] FDA rounding rules reviewed
[ ] % Daily Values reviewed
[ ] Final label reviewed before commercial use
"""
    else:
        panel = f"""{food_name}

Ingredients: {ingredient_list}

{allergen_text}

Nutrition Facts Table - Draft Review
Per serving
Calories {fmt(per_serving.get('calories'))}
Fat {fmt(per_serving.get('total_fat_g'))} g
Saturated {fmt(per_serving.get('saturated_fat_g'))} g
Trans {fmt(per_serving.get('trans_fat_g'))} g
Carbohydrate {fmt(per_serving.get('total_carbs_g'))} g
Fibre {fmt(per_serving.get('dietary_fiber_g'))} g
Sugars {fmt(per_serving.get('total_sugars_g'))} g
Protein {fmt(per_serving.get('protein_g'))} g
Cholesterol {fmt(per_serving.get('cholesterol_mg'))} mg
Sodium {fmt(per_serving.get('sodium_mg'))} mg
Potassium {fmt(per_serving.get('potassium_mg'))} mg
Calcium {fmt(per_serving.get('calcium_mg'))} mg
Iron {fmt(per_serving.get('iron_mg'))} mg

Canada label review checklist:
[ ] Nutrition Facts table format reviewed
[ ] Bilingual requirements reviewed if applicable
[ ] Ingredient order verified
[ ] Priority allergens reviewed
[ ] Human compliance review completed
"""
    return panel, ingredient_list, allergen_text, per_serving, total, allergens


def export_recipe_excel(recipe, country):
    panel, ingredient_list, allergen_text, per_serving, total, allergens = label_text(recipe, country)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([{
            "Country/Profile": country,
            "Recipe Internal Name": recipe["name"],
            "Consumer Name": recipe["consumer_name"],
            "Servings": recipe["servings"],
            "Ingredients": ingredient_list,
            "Allergens": ", ".join(sorted(allergens)),
            "Allergen Declaration": allergen_text,
        }]).to_excel(writer, sheet_name="Label Summary", index=False)
        pd.DataFrame([per_serving]).to_excel(writer, sheet_name="Nutrition Per Serving", index=False)
        pd.DataFrame([total]).to_excel(writer, sheet_name="Nutrition Full Batch", index=False)
        pd.DataFrame(recipe.get("items", [])).to_excel(writer, sheet_name="Recipe Items", index=False)
        pd.DataFrame({"Label Text": panel.splitlines()}).to_excel(writer, sheet_name="Label Copy", index=False)
    return output.getvalue()


def export_recipe_pdf(recipe, country):
    panel, *_ = label_text(recipe, country)
    output = BytesIO()
    page_size = A4 if country.startswith("UK") else letter
    c = canvas.Canvas(output, pagesize=page_size)
    width, height = page_size
    x = 0.65 * inch
    y = height - 0.75 * inch
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "Label Draft / Compliance Review")
    y -= 0.35 * inch
    c.setFont("Helvetica", 9)
    for raw_line in panel.splitlines():
        line = raw_line[:110]
        if y < 0.6 * inch:
            c.showPage()
            y = height - 0.75 * inch
            c.setFont("Helvetica", 9)
        if raw_line.strip() == recipe["consumer_name"]:
            c.setFont("Helvetica-Bold", 12)
            c.drawString(x, y, line)
            c.setFont("Helvetica", 9)
        else:
            c.drawString(x, y, line)
        y -= 0.18 * inch
    c.save()
    return output.getvalue()


def export_all_excel(country):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        product_dataframe(st.session_state.products).to_excel(writer, sheet_name="Products", index=False)
        rows = []
        for r in st.session_state.recipes:
            panel, ingredient_list, allergen_text, per_serving, total, allergens = label_text(r, country)
            rows.append({
                "Country/Profile": country,
                "Recipe": r["name"],
                "Consumer Name": r["consumer_name"],
                "Servings": r["servings"],
                "Ingredients": ingredient_list,
                "Allergens": ", ".join(sorted(allergens)),
                "Allergen Declaration": allergen_text,
                **{f"Per Serving {k}": v for k, v in per_serving.items()},
                **{f"Batch {k}": v for k, v in total.items()},
            })
        pd.DataFrame(rows).to_excel(writer, sheet_name="Recipe Labels", index=False)
        menu_rows = []
        for m in st.session_state.menus:
            for recipe in m["recipes"]:
                menu_rows.append({"Menu": m["name"], "Category": m["category"], "Recipe": recipe})
        pd.DataFrame(menu_rows).to_excel(writer, sheet_name="Menus", index=False)
    return output.getvalue()


st.title("Food Intelligence + Recipe Labeling App")

tabs = st.tabs(["Dashboard", "Add Product", "Recipe Builder", "Create Menu", "Export"])

with tabs[0]:
    st.header("Dashboard")
    c1, c2, c3 = st.columns(3)
    c1.metric("Products / Ingredients", len(st.session_state.products))
    c2.metric("Recipes", len(st.session_state.recipes))
    c3.metric("Menus", len(st.session_state.menus))
    if st.session_state.products:
        st.subheader("Customer Product Database")
        st.dataframe(product_dataframe(st.session_state.products), use_container_width=True)

with tabs[1]:
    st.header("Add Product / Ingredient")
    internal = st.text_input("Internal Name", placeholder="Internal SKU or prep name")
    consumer = st.text_input("Consumer-Facing Name", placeholder="Name shown on labels")
    supplier = st.text_input("Supplier")
    default_text = """Ingredients: wheat flour, sugar, salt, soy lecithin
Nutrition: Calories 120 Total Fat 2g Saturated Fat 1g Total Carbohydrate 24g Sugars 5g Protein 4g Sodium 200mg"""
    text = st.text_area("Paste product specification text", default_text, height=220)
    if st.button("Parse and Save Product"):
        if not internal:
            st.warning("Internal name is required.")
        else:
            p = make_product(internal, consumer or internal, supplier, text)
            st.session_state.products.append(p)
            st.success("Product saved.")
            st.json(p)

with tabs[2]:
    st.header("Recipe Builder")
    st.subheader("Consolidated Ingredient/Product Search")
    query = st.text_input("Search customer database + USDA + Open Food Facts", placeholder="Start typing: chicken, flour, milk, cheese...")
    if len(query.strip()) >= 3:
        if st.button("Search databases"):
            st.session_state.search_results = combined_search(query)
    elif query:
        st.caption("Type at least 3 characters to search.")
    if st.session_state.search_results:
        st.write(f"Results: {len(st.session_state.search_results)}")
        for idx, result in enumerate(st.session_state.search_results[:50]):
            with st.expander(f"{idx + 1}. [{result['source']}] {result['name']}"):
                st.write("Supplier:", result.get("supplier", ""))
                st.write("Ingredients:", ", ".join(result.get("ingredients", [])))
                st.write("Allergens:", ", ".join(result.get("allergens", [])))
                st.json(result.get("nutrition", {}))
                if st.button(f"Import as customer product #{idx + 1}", key=f"import_{idx}"):
                    st.session_state.products.append({
                        "internal_name": result["name"],
                        "consumer_name": result["name"],
                        "supplier": result.get("supplier", result["source"]),
                        "ingredients": result.get("ingredients", []),
                        "allergens": result.get("allergens", []),
                        "nutrition": result.get("nutrition", blank_nutrition()),
                        "raw_text": result.get("raw_text", ""),
                        "source": result["source"]
                    })
                    st.success("Imported into customer database.")
    st.divider()
    st.subheader("Create Recipe")
    recipe_internal = st.text_input("Recipe Internal Name")
    recipe_consumer = st.text_input("Recipe Consumer-Facing Name")
    servings = st.number_input("Number of servings", min_value=1, value=1)
    recipe_items = []
    product_names = [p["consumer_name"] for p in st.session_state.products]
    selected_products = st.multiselect("Add products/ingredients", product_names)
    for name in selected_products:
        c1, c2 = st.columns([1, 1])
        amount = c1.number_input(f"Amount - {name}", min_value=0.0, value=1.0, step=0.25, key=f"amt_{name}")
        unit = c2.selectbox(f"Unit - {name}", COMMON_UNITS, key=f"unit_{name}")
        recipe_items.append({"type": "product", "name": name, "amount": amount, "unit": unit})
    recipe_names = [r["name"] for r in st.session_state.recipes]
    selected_subrecipes = st.multiselect("Add saved recipes as subrecipes", recipe_names)
    for name in selected_subrecipes:
        c1, c2 = st.columns([1, 1])
        amount = c1.number_input(f"Amount - subrecipe {name}", min_value=0.0, value=1.0, step=0.25, key=f"subamt_{name}")
        unit = c2.selectbox(f"Unit - subrecipe {name}", COMMON_UNITS, key=f"subunit_{name}")
        recipe_items.append({"type": "recipe", "name": name, "amount": amount, "unit": unit})
    if st.button("Save Recipe"):
        if not recipe_internal:
            st.warning("Recipe internal name is required.")
        else:
            recipe = {"name": recipe_internal, "consumer_name": recipe_consumer or recipe_internal, "servings": servings, "items": recipe_items}
            st.session_state.recipes.append(recipe)
            st.success("Recipe saved. Label outputs are shown below for saved recipes.")
    if st.session_state.recipes:
        st.subheader("Saved Recipe Label Preview + Exports")
        selected_recipe_name = st.selectbox("Select saved recipe", [r["name"] for r in st.session_state.recipes], key="saved_recipe_select")
        country = st.selectbox("Select country/profile", COUNTRIES, key="label_country")
        recipe = next(r for r in st.session_state.recipes if r["name"] == selected_recipe_name)
        panel, ingredient_list, allergen_text, per_serving, total, allergens = label_text(recipe, country)
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("Nutrition Facts / Declaration Panel")
            st.text_area("Label text", panel, height=420)
        with col2:
            st.subheader("Ingredient List")
            st.text_area("Ingredients", ingredient_list, height=140)
            st.subheader("Allergen Declaration")
            st.text_area("Allergens", allergen_text, height=100)
            st.subheader("Per Serving Nutrition")
            st.json(per_serving)
        st.download_button("Export Selected Recipe Label - Excel", data=export_recipe_excel(recipe, country), file_name=f"{recipe['name']}_label.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.download_button("Export Selected Recipe Label - PDF", data=export_recipe_pdf(recipe, country), file_name=f"{recipe['name']}_label.pdf", mime="application/pdf")

with tabs[3]:
    st.header("Create Menu")
    menu_name = st.text_input("Menu Name")
    category = st.text_input("Menu Category", placeholder="Breakfast, Entrees, Desserts, Specials")
    selected_recipes = st.multiselect("Select recipes for this menu/category", [r["name"] for r in st.session_state.recipes])
    if st.button("Save Menu Category"):
        if not menu_name or not category:
            st.warning("Menu name and category are required.")
        else:
            st.session_state.menus.append({"name": menu_name, "category": category, "recipes": selected_recipes})
            st.success("Menu category saved.")
    if st.session_state.menus:
        st.subheader("Menus")
        for menu in st.session_state.menus:
            with st.expander(f"{menu['name']} - {menu['category']}"):
                st.write(menu["recipes"])

with tabs[4]:
    st.header("Export All")
    country = st.selectbox("Export country/profile", COUNTRIES, key="export_country")
    if st.session_state.recipes or st.session_state.products:
        st.download_button("Download Full Workbook Excel", data=export_all_excel(country), file_name="food_intelligence_export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Add products and recipes before exporting.")
    st.info("Exports and label panels are compliance-review aids. Confirm legal naming, serving sizes, ingredient order, allergen emphasis, rounding rules, and final label format before commercial use.")
