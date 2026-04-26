import re
import requests
import pandas as pd
import streamlit as st
from io import BytesIO

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

UK_ALLERGENS = {
    "celery": ["celery"],
    "cereals containing gluten": ["wheat", "barley", "rye", "oats", "spelt", "gluten"],
    "crustaceans": ["crab", "lobster", "shrimp", "prawn", "crustacean"],
    "eggs": ["egg"],
    "fish": ["fish"],
    "lupin": ["lupin"],
    "milk": ["milk", "cheese", "butter", "cream", "whey", "casein"],
    "molluscs": ["mussel", "oyster", "clam", "scallop", "mollusc"],
    "mustard": ["mustard"],
    "nuts": ["almond", "hazelnut", "walnut", "cashew", "pecan", "brazil nut", "pistachio", "macadamia"],
    "peanuts": ["peanut"],
    "sesame": ["sesame"],
    "soybeans": ["soy", "soya", "soybean"],
    "sulphur dioxide and sulphites": ["sulphite", "sulfite", "sulphur dioxide", "sulfur dioxide"]
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


def parse_nutrients(text):
    lower = text.lower()
    patterns = {
        "calories": r"calories\D*(\d+\.?\d*)",
        "energy_kj": r"(energy|kj)\D*(\d+\.?\d*)",
        "total_fat_g": r"(total fat|fat)\D*(\d+\.?\d*)",
        "saturated_fat_g": r"(saturated fat|saturates)\D*(\d+\.?\d*)",
        "trans_fat_g": r"trans fat\D*(\d+\.?\d*)",
        "cholesterol_mg": r"cholesterol\D*(\d+\.?\d*)",
        "sodium_mg": r"sodium\D*(\d+\.?\d*)",
        "total_carbs_g": r"(total carbohydrate|carbohydrate|carbs)\D*(\d+\.?\d*)",
        "dietary_fiber_g": r"(dietary fiber|fibre|fiber)\D*(\d+\.?\d*)",
        "total_sugars_g": r"(total sugars|sugars|sugar)\D*(\d+\.?\d*)",
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
            nutrition[key] = safe_float(match.groups()[-1])

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

    return [i.strip(" :.\n") for i in part.split(",") if i.strip(" :.\n")]


def detect_allergens(text, ingredients=None):
    haystack = text.lower()
    if ingredients:
        haystack += " " + " ".join(ingredients).lower()

    found = []
    for allergen, keywords in UK_ALLERGENS.items():
        if any(k in haystack for k in keywords):
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


def search_open_food_facts(query, limit=25):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": limit
    }

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
    params = {
        "query": query,
        "pageSize": limit,
        "api_key": api_key
    }

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
        searchable = " ".join([
            p.get("internal_name", ""),
            p.get("consumer_name", ""),
            p.get("supplier", ""),
            " ".join(p.get("ingredients", [])),
            " ".join(p.get("allergens", []))
        ]).lower()

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
        return blank_nutrition(), set(["CIRCULAR RECIPE WARNING"])

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


def emphasize_allergens(text):
    result = text
    for allergen, keywords in UK_ALLERGENS.items():
        for word in keywords:
            result = re.sub(
                rf"\b({re.escape(word)})\b",
                lambda m: m.group(1).upper(),
                result,
                flags=re.IGNORECASE
            )
    return result


def build_ingredient_list_for_recipe(recipe, parenthesize_subrecipes=True, emphasize=True):
    parts = []

    for item in recipe.get("items", []):
        if item["type"] == "product":
            p = next((x for x in st.session_state.products if x["consumer_name"] == item["name"]), None)
            if p:
                name = p.get("consumer_name", item["name"])
                parts.append((item["amount"], name))

        elif item["type"] == "recipe":
            r = next((x for x in st.session_state.recipes if x["name"] == item["name"]), None)
            if r:
                if parenthesize_subrecipes:
                    sub_parts = build_ingredient_list_for_recipe(r, True, False)
                    display = f"{r['consumer_name']} ({sub_parts})"
                else:
                    display = r["consumer_name"]
                parts.append((item["amount"], display))

    parts.sort(key=lambda x: x[0], reverse=True)
    text = ", ".join([p[1] for p in parts])

    if emphasize:
        text = emphasize_allergens(text)

    return text


def uk_nutrition_panel(name, nutrition, servings=1):
    per_serving = scale_nutrition(nutrition, 1 / max(servings, 1))
    return f"""UK Nutrition Declaration - Compliance Review Draft

Food Name: {name}
Servings: {servings}

Typical values per serving:
Energy: {per_serving.get('energy_kj', 0)} kJ / {per_serving.get('calories', 0)} kcal
Fat: {per_serving.get('total_fat_g', 0)} g
of which saturates: {per_serving.get('saturated_fat_g', 0)} g
Carbohydrate: {per_serving.get('total_carbs_g', 0)} g
of which sugars: {per_serving.get('total_sugars_g', 0)} g
Protein: {per_serving.get('protein_g', 0)} g
Salt: {per_serving.get('salt_g', 0)} g

Review note: confirm serving size, legal naming, allergen emphasis, and final label format before use.
"""


def export_excel():
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        product_dataframe(st.session_state.products).to_excel(writer, sheet_name="Products", index=False)

        recipe_rows = []
        for r in st.session_state.recipes:
            total, allergens = recipe_total(r)
            ingredient_list = build_ingredient_list_for_recipe(r)
            recipe_rows.append({
                "Recipe": r["name"],
                "Consumer Name": r["consumer_name"],
                "Servings": r["servings"],
                "Ingredients": ingredient_list,
                "Allergens": ", ".join(sorted(allergens)),
                **total
            })

        pd.DataFrame(recipe_rows).to_excel(writer, sheet_name="Recipes", index=False)

        menu_rows = []
        for m in st.session_state.menus:
            for recipe in m["recipes"]:
                menu_rows.append({
                    "Menu": m["name"],
                    "Category": m["category"],
                    "Recipe": recipe
                })
        pd.DataFrame(menu_rows).to_excel(writer, sheet_name="Menus", index=False)

    return output.getvalue()


st.title("Food Intelligence + Recipe Labeling App")

tabs = st.tabs([
    "Dashboard",
    "Add Product",
    "Recipe Builder",
    "Create Menu",
    "Copy Center",
    "Export"
])

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
    query = st.text_input("Search customer database + USDA + Open Food Facts")

    if st.button("Search"):
        if query:
            st.session_state.search_results = combined_search(query)
        else:
            st.warning("Enter a keyword first.")

    if st.session_state.search_results:
        st.write(f"Results: {len(st.session_state.search_results)}")

        for idx, result in enumerate(st.session_state.search_results):
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
            recipe = {
                "name": recipe_internal,
                "consumer_name": recipe_consumer or recipe_internal,
                "servings": servings,
                "items": recipe_items
            }
            st.session_state.recipes.append(recipe)
            st.success("Recipe saved.")

    if st.session_state.recipes:
        st.subheader("Saved Recipes")
        for recipe in st.session_state.recipes:
            total, allergens = recipe_total(recipe)
            with st.expander(recipe["consumer_name"]):
                st.write("Servings:", recipe["servings"])
                st.write("Items:", recipe["items"])
                st.write("Allergens:", ", ".join(sorted(allergens)))
                st.subheader("Total Nutrition")
                st.json(total)
                st.subheader("Per Serving Nutrition")
                st.json(scale_nutrition(total, 1 / max(recipe["servings"], 1)))
                st.subheader("Ingredient List Draft")
                st.text_area("Copy ingredient list", build_ingredient_list_for_recipe(recipe), height=100)

with tabs[3]:
    st.header("Create Menu")

    menu_name = st.text_input("Menu Name")
    category = st.text_input("Menu Category", placeholder="Breakfast, Entrees, Desserts, Specials")
    selected_recipes = st.multiselect(
        "Select recipes for this menu/category",
        [r["name"] for r in st.session_state.recipes]
    )

    if st.button("Save Menu Category"):
        if not menu_name or not category:
            st.warning("Menu name and category are required.")
        else:
            st.session_state.menus.append({
                "name": menu_name,
                "category": category,
                "recipes": selected_recipes
            })
            st.success("Menu category saved.")

    if st.session_state.menus:
        st.subheader("Menus")
        for menu in st.session_state.menus:
            with st.expander(f"{menu['name']} - {menu['category']}"):
                st.write(menu["recipes"])

with tabs[4]:
    st.header("Copy Center")

    if not st.session_state.recipes:
        st.info("Create a recipe first.")
    else:
        recipe_name = st.selectbox("Choose recipe", [r["name"] for r in st.session_state.recipes])
        recipe = next(r for r in st.session_state.recipes if r["name"] == recipe_name)

        total, allergens = recipe_total(recipe)
        ingredient_list = build_ingredient_list_for_recipe(recipe)
        allergen_declaration = "Contains: " + ", ".join(sorted(allergens)) if allergens else "No declarable allergens detected."

        panel = uk_nutrition_panel(recipe["consumer_name"], total, recipe["servings"])

        st.subheader("Nutrition Panel")
        st.text_area("Copy nutrition panel", panel, height=260)

        st.subheader("Ingredient List")
        st.text_area("Copy ingredient list", ingredient_list, height=120)

        st.subheader("Allergen Declaration")
        st.text_area("Copy allergen declaration", allergen_declaration, height=80)

        st.subheader("Combined Label Draft")
        combined = f"""{recipe['consumer_name']}

Ingredients: {ingredient_list}

{allergen_declaration}

{panel}
"""
        st.text_area("Copy combined label draft", combined, height=420)

with tabs[5]:
    st.header("Export")

    if st.button("Prepare Excel Export"):
        data = export_excel()
        st.download_button(
            "Download Food Intelligence Workbook",
            data=data,
            file_name="food_intelligence_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.info("Exports are compliance review aids and should be checked by a qualified reviewer before commercial label use.")
