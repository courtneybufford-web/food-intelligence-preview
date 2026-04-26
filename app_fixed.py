import re
from io import BytesIO
import pandas as pd
import requests
import streamlit as st

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except Exception:
    letter = None
    canvas = None

st.set_page_config(page_title="Food Intelligence App", layout="wide")

COMMON_UNITS = ["g", "kg", "mg", "oz", "lb", "ml", "l", "tsp", "tbsp", "cup", "fl oz", "pint", "quart", "gallon", "each", "piece", "slice", "serving", "portion"]
NUTRIENT_KEYS = ["calories", "energy_kj", "total_fat_g", "saturated_fat_g", "trans_fat_g", "cholesterol_mg", "sodium_mg", "total_carbs_g", "dietary_fiber_g", "total_sugars_g", "added_sugars_g", "protein_g", "vitamin_d_mcg", "calcium_mg", "iron_mg", "potassium_mg", "salt_g"]
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

for key, default in {"products": [], "recipes": [], "menus": [], "recipe_draft_items": [], "search_results": []}.items():
    if key not in st.session_state:
        st.session_state[key] = default


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


def product_name(product):
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
        match = re.search(pattern, lower)
        if match:
            nutrition[key] = safe_float(match.group(1))
    if nutrition["salt_g"] == 0 and nutrition["sodium_mg"] > 0:
        nutrition["salt_g"] = round(nutrition["sodium_mg"] * 2.5 / 1000, 3)
    return nutrition


def parse_ingredients(text):
    lower = text.lower()
    if "ingredients" not in lower:
        return []
    part = lower.split("ingredients", 1)[1]
    for stop in ["nutrition", "allergen", "contains"]:
        if stop in part:
            part = part.split(stop, 1)[0]
    return [i.strip(" :.;\n") for i in part.split(",") if i.strip(" :.;\n")]


def detect_allergens(text, ingredients=None):
    haystack = (text or "").lower()
    if ingredients:
        haystack += " " + " ".join(ingredients).lower()
    found = []
    for allergen, keywords in UK_ALLERGENS.items():
        if any(k in haystack for k in keywords):
            found.append(allergen)
    return sorted(set(found))


def make_product(internal, consumer, supplier, text, source="Customer"):
    ingredients = parse_ingredients(text)
    nutrition = parse_nutrients(text)
    return {"internal_name": internal, "consumer_name": consumer or internal, "supplier": supplier, "ingredients": ingredients, "allergens": detect_allergens(text, ingredients), "nutrition": nutrition, "raw_text": text, "source": source}


def products_dataframe(products):
    rows = []
    for i, p in enumerate(products):
        n = p.get("nutrition", blank_nutrition())
        rows.append({"ID": i, "Name": product_name(p), "Internal Name": p.get("internal_name", ""), "Supplier": p.get("supplier", ""), "Source": p.get("source", "Customer"), "Ingredients": ", ".join(p.get("ingredients", [])), "Allergens": ", ".join(p.get("allergens", [])), "Calories": n.get("calories", 0), "Fat g": n.get("total_fat_g", 0), "Saturates g": n.get("saturated_fat_g", 0), "Carbs g": n.get("total_carbs_g", 0), "Sugars g": n.get("total_sugars_g", 0), "Protein g": n.get("protein_g", 0), "Salt g": n.get("salt_g", 0)})
    return pd.DataFrame(rows)


def nutrition_from_off(item):
    nutriments = item.get("nutriments", {})
    n = blank_nutrition()
    n["calories"] = safe_float(nutriments.get("energy-kcal_100g"))
    n["energy_kj"] = safe_float(nutriments.get("energy-kj_100g"))
    n["total_fat_g"] = safe_float(nutriments.get("fat_100g"))
    n["saturated_fat_g"] = safe_float(nutriments.get("saturated-fat_100g"))
    n["total_carbs_g"] = safe_float(nutriments.get("carbohydrates_100g"))
    n["total_sugars_g"] = safe_float(nutriments.get("sugars_100g"))
    n["dietary_fiber_g"] = safe_float(nutriments.get("fiber_100g"))
    n["protein_g"] = safe_float(nutriments.get("proteins_100g"))
    n["salt_g"] = safe_float(nutriments.get("salt_100g"))
    n["sodium_mg"] = safe_float(nutriments.get("sodium_100g")) * 1000
    return n


def search_open_food_facts(query, limit=15):
    try:
        response = requests.get("https://world.openfoodfacts.org/cgi/search.pl", params={"search_terms": query, "search_simple": 1, "action": "process", "json": 1, "page_size": limit}, timeout=8)
        data = response.json()
    except Exception:
        return []
    results = []
    for item in data.get("products", []):
        name = item.get("product_name") or item.get("generic_name") or "Unnamed Open Food Facts Product"
        ingredients_text = item.get("ingredients_text", "")
        ingredients = [x.strip() for x in ingredients_text.split(",") if x.strip()]
        results.append({"source": "Open Food Facts", "name": name, "supplier": item.get("brands", ""), "ingredients": ingredients, "allergens": detect_allergens(ingredients_text, ingredients), "nutrition": nutrition_from_off(item), "raw_text": ingredients_text})
    return results


def search_usda(query, limit=15):
    api_key = st.secrets.get("USDA_API_KEY", "")
    if not api_key:
        return []
    try:
        response = requests.get("https://api.nal.usda.gov/fdc/v1/foods/search", params={"query": query, "pageSize": limit, "api_key": api_key}, timeout=8)
        data = response.json()
    except Exception:
        return []
    results = []
    for food in data.get("foods", []):
        n = blank_nutrition()
        for nutrient in food.get("foodNutrients", []):
            nutrient_name = nutrient.get("nutrientName", "").lower()
            value = safe_float(nutrient.get("value"))
            unit = nutrient.get("unitName", "").lower()
            if "energy" in nutrient_name and "kcal" in unit:
                n["calories"] = value
            elif nutrient_name == "protein":
                n["protein_g"] = value
            elif "total lipid" in nutrient_name or nutrient_name == "total fat":
                n["total_fat_g"] = value
            elif "saturated" in nutrient_name:
                n["saturated_fat_g"] = value
            elif "carbohydrate" in nutrient_name:
                n["total_carbs_g"] = value
            elif "sugars" in nutrient_name:
                n["total_sugars_g"] = value
            elif "fiber" in nutrient_name:
                n["dietary_fiber_g"] = value
            elif nutrient_name == "sodium, na":
                n["sodium_mg"] = value
                n["salt_g"] = round(value * 2.5 / 1000, 3)
        desc = food.get("description", "USDA Food").title()
        results.append({"source": "USDA", "name": desc, "supplier": "USDA FoodData Central", "ingredients": [desc.lower()], "allergens": detect_allergens(desc), "nutrition": n, "raw_text": desc})
    return results


def combined_search(query):
    results = []
    q = query.lower().strip()
    for p in st.session_state.products:
        text = " ".join([product_name(p), p.get("supplier", ""), " ".join(p.get("ingredients", [])), " ".join(p.get("allergens", []))]).lower()
        if q in text:
            results.append({"source": "Customer Database", "name": product_name(p), "supplier": p.get("supplier", ""), "ingredients": p.get("ingredients", []), "allergens": p.get("allergens", []), "nutrition": p.get("nutrition", blank_nutrition()), "raw_text": p.get("raw_text", "")})
    results.extend(search_usda(query))
    results.extend(search_open_food_facts(query))
    return results


def add_result_to_products(result):
    product = {"internal_name": result["name"], "consumer_name": result["name"], "supplier": result.get("supplier", result.get("source", "")), "ingredients": result.get("ingredients", []), "allergens": result.get("allergens", []), "nutrition": result.get("nutrition", blank_nutrition()), "raw_text": result.get("raw_text", ""), "source": result.get("source", "External")}
    st.session_state.products.append(product)
    return product_name(product)


def render_search_results(results):
    if not results:
        st.info("No results found.")
        return
    for idx, result in enumerate(results):
        icon = "👤" if result["source"] == "Customer Database" else ("✅" if result["source"] == "USDA" else "👥")
        badge = "CUSTOMER" if result["source"] == "Customer Database" else result["source"]
        n = result.get("nutrition", blank_nutrition())
        with st.container(border=True):
            c0, c1, c2, c3 = st.columns([0.4, 4.6, 1.2, 1.1])
            c0.markdown(f"### {icon}")
            c1.markdown(f"**{result['name']}**  `{badge}`")
            c1.caption(f"{fmt(n.get('calories'))} kcal | Protein {fmt(n.get('protein_g'))}g | Fat {fmt(n.get('total_fat_g'))}g | Salt {fmt(n.get('salt_g'), 2)}g")
            if result.get("allergens"):
                c1.warning("Allergens: " + ", ".join(result.get("allergens", [])))
            if c2.button("+ Add to Recipe", key=f"add_recipe_{idx}_{result['source']}_{result['name']}"):
                name = add_result_to_products(result)
                st.session_state.recipe_draft_items.append({"type": "product", "name": name, "amount": 1.0, "unit": "serving"})
                st.success(f"Added {name} to recipe draft.")
                st.rerun()
            with c3.expander("Preview"):
                st.write("Ingredients:", ", ".join(result.get("ingredients", [])) or "Not available")
                st.json(n)


def scale_nutrition(n, factor):
    return {k: round(safe_float(n.get(k)) * factor, 3) for k in NUTRIENT_KEYS}


def add_nutrition(total, n, multiplier=1.0):
    out = dict(total)
    for k in NUTRIENT_KEYS:
        out[k] = safe_float(out.get(k)) + safe_float(n.get(k)) * multiplier
    return out


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
            p = next((x for x in st.session_state.products if product_name(x) == item["name"]), None)
            if p:
                total = add_nutrition(total, p["nutrition"], item.get("amount", 1))
                allergens.update(p.get("allergens", []))
        elif item["type"] == "recipe":
            r = next((x for x in st.session_state.recipes if x["name"] == item["name"]), None)
            if r:
                sub_total, sub_allergens = recipe_total(r, seen)
                total = add_nutrition(total, sub_total, item.get("amount", 1))
                allergens.update(sub_allergens)
    return total, allergens


def emphasize_allergens(text):
    output = text
    for keywords in UK_ALLERGENS.values():
        for word in keywords:
            output = re.sub(rf"\b({re.escape(word)})\b", lambda m: m.group(1).upper(), output, flags=re.IGNORECASE)
    return output


def recipe_ingredient_list(recipe):
    parts = []
    for item in recipe.get("items", []):
        if item["type"] == "product":
            p = next((x for x in st.session_state.products if product_name(x) == item["name"]), None)
            if p:
                parts.append((safe_float(item.get("amount", 1)), product_name(p)))
        elif item["type"] == "recipe":
            r = next((x for x in st.session_state.recipes if x["name"] == item["name"]), None)
            if r:
                parts.append((safe_float(item.get("amount", 1)), f"{r['consumer_name']} ({recipe_ingredient_list(r)})"))
    parts.sort(key=lambda row: row[0], reverse=True)
    return emphasize_allergens(", ".join([p[1] for p in parts]))


def uk_label(recipe):
    total, allergens = recipe_total(recipe)
    per_serving = scale_nutrition(total, 1 / max(recipe.get("servings", 1), 1))
    ingredients = recipe_ingredient_list(recipe)
    allergen_line = "Contains: " + ", ".join(sorted(allergens)) if allergens else "No declarable allergens detected."
    return f"""{recipe['consumer_name']}

Ingredients: {ingredients}

{allergen_line}

Nutrition Declaration - typical values per serving
Energy: {fmt(per_serving['energy_kj'])} kJ / {fmt(per_serving['calories'])} kcal
Fat: {fmt(per_serving['total_fat_g'])} g
of which saturates: {fmt(per_serving['saturated_fat_g'])} g
Carbohydrate: {fmt(per_serving['total_carbs_g'])} g
of which sugars: {fmt(per_serving['total_sugars_g'])} g
Protein: {fmt(per_serving['protein_g'])} g
Salt: {fmt(per_serving['salt_g'], 2)} g

Review note: This is a compliance-review draft. Confirm final label before commercial use.
"""


def excel_export():
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        products_dataframe(st.session_state.products).to_excel(writer, sheet_name="Products", index=False)
        recipe_rows = []
        for r in st.session_state.recipes:
            total, allergens = recipe_total(r)
            recipe_rows.append({"Recipe": r["name"], "Consumer Name": r["consumer_name"], "Servings": r["servings"], "Ingredients": recipe_ingredient_list(r), "Allergens": ", ".join(sorted(allergens)), **total})
        pd.DataFrame(recipe_rows).to_excel(writer, sheet_name="Recipes", index=False)
    return output.getvalue()


def pdf_label(label_text):
    if canvas is None:
        return b"PDF export unavailable. Add reportlab to requirements.txt."
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50
    for line in label_text.splitlines():
        if y < 50:
            c.showPage()
            y = height - 50
        c.drawString(50, y, line[:110])
        y -= 15
    c.save()
    return buffer.getvalue()


st.title("Food Intelligence + Recipe Labeling App")

with st.sidebar:
    st.header("Controls")
    if st.button("Load Demo Products"):
        demo = [
            ("chicken", "Chicken", "Demo", "Ingredients: chicken breast Nutrition: Calories 165 Protein 31g Fat 4g Sodium 74mg"),
            ("bun", "Wheat Bun", "Demo", "Ingredients: wheat flour, water, yeast, salt Nutrition: Calories 140 Protein 5g Fat 2g Carbohydrate 26g Sugars 4g Sodium 220mg"),
        ]
        for d in demo:
            st.session_state.products.append(make_product(*d))
        st.rerun()
    if st.button("Clear All"):
        st.session_state.products = []
        st.session_state.recipes = []
        st.session_state.menus = []
        st.session_state.recipe_draft_items = []
        st.session_state.search_results = []
        st.rerun()

tab_dashboard, tab_add, tab_recipe, tab_menu, tab_export = st.tabs(["Dashboard", "Add Product", "Recipe Builder", "Create Menu", "Export"])

with tab_dashboard:
    st.header("Dashboard")
    c1, c2, c3 = st.columns(3)
    c1.metric("Products", len(st.session_state.products))
    c2.metric("Recipes", len(st.session_state.recipes))
    c3.metric("Menus", len(st.session_state.menus))
    if st.session_state.products:
        st.dataframe(products_dataframe(st.session_state.products), use_container_width=True)
    else:
        st.info("Add products manually or search databases in Recipe Builder.")

with tab_add:
    st.header("Add Product / Ingredient")
    internal = st.text_input("Internal Name")
    consumer = st.text_input("Consumer-Facing Name")
    supplier = st.text_input("Supplier")
    text = st.text_area("Paste product spec text", "Ingredients: wheat flour, sugar, salt, soy lecithin\nNutrition: Calories 120 Total Fat 2g Saturated Fat 1g Carbohydrate 24g Sugars 5g Protein 4g Sodium 200mg", height=180)
    if st.button("Parse and Save Product"):
        if not internal:
            st.warning("Internal name is required.")
        else:
            st.session_state.products.append(make_product(internal, consumer or internal, supplier, text))
            st.success("Product saved.")
            st.rerun()

with tab_recipe:
    st.header("Recipe Builder")
    st.subheader("Search ingredients and databases")
    query = st.text_input("Search", placeholder="Start typing: chicken, flour, milk...")
    if len(query.strip()) >= 2:
        st.session_state.search_results = combined_search(query)
        render_search_results(st.session_state.search_results[:30])
    elif query:
        st.caption("Type at least 2 characters.")

    st.divider()
    st.subheader("Current Recipe Draft")
    if st.session_state.recipe_draft_items:
        new_items = []
        for i, item in enumerate(st.session_state.recipe_draft_items):
            c1, c2, c3, c4 = st.columns([3, 1, 1, 0.8])
            c1.write(item["name"])
            amount = c2.number_input("Amount", value=safe_float(item.get("amount", 1)), min_value=0.0, step=0.25, key=f"draft_amt_{i}")
            unit = c3.selectbox("Unit", COMMON_UNITS, index=COMMON_UNITS.index(item.get("unit", "serving")) if item.get("unit", "serving") in COMMON_UNITS else 0, key=f"draft_unit_{i}")
            remove = c4.checkbox("Remove", key=f"remove_{i}")
            if not remove:
                new_items.append({**item, "amount": amount, "unit": unit})
        st.session_state.recipe_draft_items = new_items
    else:
        st.info("Use + Add to Recipe from search results.")

    if st.session_state.products:
        st.subheader("Add saved products directly")
        product_choices = [product_name(p) for p in st.session_state.products]
        add_saved = st.multiselect("Saved products", product_choices)
        if st.button("Add selected saved products to draft"):
            for name in add_saved:
                st.session_state.recipe_draft_items.append({"type": "product", "name": name, "amount": 1.0, "unit": "serving"})
            st.rerun()

    if st.session_state.recipes:
        st.subheader("Add saved recipes as subrecipes")
        selected_subs = st.multiselect("Subrecipes", [r["name"] for r in st.session_state.recipes])
        if st.button("Add selected subrecipes to draft"):
            for name in selected_subs:
                st.session_state.recipe_draft_items.append({"type": "recipe", "name": name, "amount": 1.0, "unit": "serving"})
            st.rerun()

    st.divider()
    st.subheader("Save Recipe")
    recipe_internal = st.text_input("Recipe Internal Name")
    recipe_consumer = st.text_input("Recipe Consumer-Facing Name")
    servings = st.number_input("Number of servings", min_value=1, value=1)
    if st.button("Save Recipe"):
        if not recipe_internal:
            st.warning("Recipe internal name is required.")
        elif not st.session_state.recipe_draft_items:
            st.warning("Add at least one item to the recipe draft.")
        else:
            st.session_state.recipes.append({"name": recipe_internal, "consumer_name": recipe_consumer or recipe_internal, "servings": servings, "items": list(st.session_state.recipe_draft_items)})
            st.session_state.recipe_draft_items = []
            st.success("Recipe saved.")
            st.rerun()

    if st.session_state.recipes:
        st.subheader("Saved Recipe Label Preview and Exports")
        selected = st.selectbox("Select saved recipe", [r["name"] for r in st.session_state.recipes])
        recipe = next(r for r in st.session_state.recipes if r["name"] == selected)
        label_text = uk_label(recipe)
        st.text_area("Label preview", label_text, height=360)
        st.download_button("Download Label Text", label_text, file_name=f"{recipe['name']}_label.txt")
        st.download_button("Download Label PDF", pdf_label(label_text), file_name=f"{recipe['name']}_label.pdf", mime="application/pdf")

with tab_menu:
    st.header("Create Menu")
    menu_name = st.text_input("Menu Name")
    category = st.text_input("Category", placeholder="Breakfast, Entrees, Desserts, Specials")
    selected = st.multiselect("Select recipes", [r["name"] for r in st.session_state.recipes])
    if st.button("Save Menu Category"):
        if not menu_name or not category:
            st.warning("Menu name and category are required.")
        else:
            st.session_state.menus.append({"name": menu_name, "category": category, "recipes": selected})
            st.success("Menu saved.")
    for menu in st.session_state.menus:
        with st.expander(f"{menu['name']} - {menu['category']}"):
            st.write(menu["recipes"])

with tab_export:
    st.header("Export")
    st.download_button("Download Excel Workbook", excel_export(), file_name="food_intelligence_export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.info("Exports are compliance-review aids and should be checked before commercial label use.")
