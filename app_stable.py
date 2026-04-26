import re
from io import BytesIO
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Food Intelligence App", layout="wide")

UNITS = ["g", "kg", "mg", "oz", "lb", "ml", "l", "tsp", "tbsp", "cup", "each", "piece", "slice", "serving"]
NUTRIENTS = ["calories", "total_fat_g", "saturated_fat_g", "total_carbs_g", "total_sugars_g", "protein_g", "sodium_mg", "salt_g"]
ALLERGEN_RULES = {
    "gluten": ["wheat", "barley", "rye", "oats", "gluten"],
    "milk": ["milk", "cheese", "butter", "cream", "whey", "casein"],
    "soybeans": ["soy", "soya", "soybean"],
    "eggs": ["egg"],
    "peanuts": ["peanut"],
    "nuts": ["almond", "cashew", "walnut", "pecan", "hazelnut", "pistachio"],
    "sesame": ["sesame"],
    "fish": ["fish", "salmon", "tuna", "cod"],
    "crustaceans": ["shrimp", "prawn", "crab", "lobster"],
    "mustard": ["mustard"],
    "celery": ["celery"],
    "sulphites": ["sulphite", "sulfite", "sulphur dioxide", "sulfur dioxide"],
}

SAMPLE_DB = [
    {"name": "Chicken Breast", "source": "Sample Database", "ingredients": ["chicken breast"], "nutrition": {"calories": 165, "total_fat_g": 3.6, "saturated_fat_g": 1.0, "total_carbs_g": 0, "total_sugars_g": 0, "protein_g": 31, "sodium_mg": 74, "salt_g": 0.19}},
    {"name": "Wheat Flour", "source": "Sample Database", "ingredients": ["wheat flour"], "nutrition": {"calories": 364, "total_fat_g": 1, "saturated_fat_g": 0.2, "total_carbs_g": 76, "total_sugars_g": 0.3, "protein_g": 10, "sodium_mg": 2, "salt_g": 0.01}},
    {"name": "Whole Milk", "source": "Sample Database", "ingredients": ["milk"], "nutrition": {"calories": 61, "total_fat_g": 3.3, "saturated_fat_g": 1.9, "total_carbs_g": 4.8, "total_sugars_g": 5.1, "protein_g": 3.2, "sodium_mg": 43, "salt_g": 0.11}},
]

for key, default in {"products": [], "recipes": [], "menus": [], "draft_items": []}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def zero_nutrition():
    return {k: 0.0 for k in NUTRIENTS}

def num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0

def parse_nutrition(text):
    t = text.lower()
    patterns = {
        "calories": r"calories\D*(\d+\.?\d*)",
        "total_fat_g": r"(?:total fat|fat)\D*(\d+\.?\d*)",
        "saturated_fat_g": r"(?:saturated fat|saturates)\D*(\d+\.?\d*)",
        "total_carbs_g": r"(?:total carbohydrate|carbohydrate|carbs)\D*(\d+\.?\d*)",
        "total_sugars_g": r"(?:total sugars|sugars|sugar)\D*(\d+\.?\d*)",
        "protein_g": r"protein\D*(\d+\.?\d*)",
        "sodium_mg": r"sodium\D*(\d+\.?\d*)",
        "salt_g": r"salt\D*(\d+\.?\d*)",
    }
    n = zero_nutrition()
    for k, p in patterns.items():
        m = re.search(p, t)
        if m:
            n[k] = num(m.group(1))
    if n["salt_g"] == 0 and n["sodium_mg"]:
        n["salt_g"] = round(n["sodium_mg"] * 2.5 / 1000, 3)
    return n

def parse_ingredients(text):
    t = text.lower()
    if "ingredients" not in t:
        return []
    part = t.split("ingredients", 1)[1]
    for stop in ["nutrition", "contains", "allergen"]:
        if stop in part:
            part = part.split(stop, 1)[0]
    return [x.strip(" :.\n") for x in part.split(",") if x.strip(" :.\n")]

def detect_allergens(text, ingredients=None):
    hay = (text or "").lower() + " " + " ".join(ingredients or []).lower()
    found = []
    for allergen, words in ALLERGEN_RULES.items():
        if any(w in hay for w in words):
            found.append(allergen)
    return sorted(set(found))

def product_row(p, idx=None):
    n = p.get("nutrition", zero_nutrition())
    return {
        "ID": idx,
        "Internal Name": p.get("internal_name", ""),
        "Consumer Name": p.get("consumer_name", ""),
        "Source": p.get("source", "Customer"),
        "Ingredients": ", ".join(p.get("ingredients", [])),
        "Allergens": ", ".join(p.get("allergens", [])),
        **n,
    }

def all_products_df():
    return pd.DataFrame([product_row(p, i) for i, p in enumerate(st.session_state.products)])

def search_database(query):
    q = query.lower().strip()
    results = []
    for p in st.session_state.products:
        blob = " ".join([p.get("consumer_name", ""), p.get("internal_name", ""), " ".join(p.get("ingredients", [])), " ".join(p.get("allergens", []))]).lower()
        if q in blob:
            results.append({**p, "source": "Customer Database"})
    for item in SAMPLE_DB:
        blob = " ".join([item["name"], " ".join(item["ingredients"])]).lower()
        if q in blob:
            results.append({"internal_name": item["name"], "consumer_name": item["name"], "source": item["source"], "ingredients": item["ingredients"], "allergens": detect_allergens(item["name"], item["ingredients"]), "nutrition": item["nutrition"], "raw_text": item["name"]})
    return results

def add_nutrition(a, b, factor=1):
    out = dict(a)
    for k in NUTRIENTS:
        out[k] = round(num(out.get(k)) + num(b.get(k)) * num(factor), 3)
    return out

def recipe_total(recipe):
    total = zero_nutrition()
    allergens = set()
    for item in recipe.get("items", []):
        p = next((x for x in st.session_state.products if x.get("consumer_name") == item.get("name")), None)
        if p:
            total = add_nutrition(total, p["nutrition"], item.get("amount", 1))
            allergens.update(p.get("allergens", []))
    return total, sorted(allergens)

def emphasize(text):
    out = text
    for words in ALLERGEN_RULES.values():
        for w in words:
            out = re.sub(rf"\b({re.escape(w)})\b", lambda m: m.group(1).upper(), out, flags=re.I)
    return out

def ingredient_list(recipe):
    parts = []
    for item in recipe.get("items", []):
        p = next((x for x in st.session_state.products if x.get("consumer_name") == item.get("name")), None)
        if p:
            parts.append((num(item.get("amount")), p.get("consumer_name")))
    parts.sort(reverse=True, key=lambda x: x[0])
    return emphasize(", ".join([p[1] for p in parts]))

def label_text(recipe, country):
    total, allergens = recipe_total(recipe)
    servings = max(1, int(recipe.get("servings", 1)))
    per = {k: round(v / servings, 3) for k, v in total.items()}
    ingredients = ingredient_list(recipe)
    contains = "Contains: " + ", ".join(allergens) if allergens else "No declarable allergens detected."
    if country == "UK / Natasha's Law Review":
        title = "UK PPDS / Natasha's Law Review Draft"
    elif country == "US":
        title = "US Nutrition Facts Draft"
    else:
        title = "Canada Nutrition Facts Draft"
    return f"""{title}

Food Name: {recipe.get('consumer_name', recipe.get('name'))}
Servings: {servings}

Ingredients: {ingredients}
{contains}

Nutrition per serving:
Calories: {per['calories']}
Fat: {per['total_fat_g']} g
Saturated Fat: {per['saturated_fat_g']} g
Carbohydrate: {per['total_carbs_g']} g
Sugars: {per['total_sugars_g']} g
Protein: {per['protein_g']} g
Sodium: {per['sodium_mg']} mg
Salt: {per['salt_g']} g

Review note: This is a compliance-aid draft. Confirm legal requirements, rounding, serving size, and allergen emphasis before commercial use.
"""

def excel_bytes():
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        all_products_df().to_excel(writer, sheet_name="Products", index=False)
        rows = []
        for r in st.session_state.recipes:
            total, allergens = recipe_total(r)
            rows.append({"Recipe": r["name"], "Consumer Name": r.get("consumer_name", r["name"]), "Servings": r.get("servings", 1), "Ingredients": ingredient_list(r), "Allergens": ", ".join(allergens), **total})
        pd.DataFrame(rows).to_excel(writer, sheet_name="Recipes", index=False)
    return output.getvalue()

st.title("Food Intelligence + Recipe Labeling App")

tab_dashboard, tab_add, tab_recipe, tab_menu, tab_export = st.tabs(["Dashboard", "Add Product", "Recipe Builder", "Create Menu", "Export"])

with tab_dashboard:
    st.header("Dashboard")
    c1, c2, c3 = st.columns(3)
    c1.metric("Products", len(st.session_state.products))
    c2.metric("Recipes", len(st.session_state.recipes))
    c3.metric("Menus", len(st.session_state.menus))
    if st.session_state.products:
        st.dataframe(all_products_df(), use_container_width=True)

with tab_add:
    st.header("Add Product / Ingredient")
    internal = st.text_input("Internal Name")
    consumer = st.text_input("Consumer-Facing Name")
    supplier = st.text_input("Supplier")
    text = st.text_area("Paste product spec text", "Ingredients: wheat flour, sugar, salt\nNutrition: Calories 120 Total Fat 2g Saturated Fat 1g Carbs 24g Sugars 5g Protein 4g Sodium 200mg", height=180)
    if st.button("Parse and Save Product"):
        if not internal:
            st.warning("Internal name is required.")
        else:
            ingredients = parse_ingredients(text)
            p = {"internal_name": internal, "consumer_name": consumer or internal, "supplier": supplier, "source": "Customer", "ingredients": ingredients, "allergens": detect_allergens(text, ingredients), "nutrition": parse_nutrition(text), "raw_text": text}
            st.session_state.products.append(p)
            st.success("Saved product.")
            st.json(p)

with tab_recipe:
    st.header("Recipe Builder")
    st.subheader("Database Search")
    q = st.text_input("Search ingredients/products", placeholder="Type chicken, flour, milk...")
    if len(q.strip()) >= 2:
        results = search_database(q)
        st.write(f"{len(results)} results")
        for i, r in enumerate(results[:25]):
            col_icon, col_text, col_btn, col_prev = st.columns([0.3, 4, 1.2, 1])
            col_icon.write("👤" if r.get("source") == "Customer Database" else "🏷️")
            n = r.get("nutrition", zero_nutrition())
            col_text.markdown(f"**{r.get('consumer_name', r.get('name', 'Unnamed'))}**  `SOURCE: {r.get('source','')}`")
            col_text.caption(f"{n.get('calories',0)} cal | Protein {n.get('protein_g',0)}g | Allergens: {', '.join(r.get('allergens', [])) or 'None'}")
            if col_btn.button("+ Add to Recipe", key=f"add_{i}"):
                if not any(p.get("consumer_name") == r.get("consumer_name") for p in st.session_state.products):
                    st.session_state.products.append(r)
                st.session_state.draft_items.append({"name": r.get("consumer_name"), "amount": 1.0, "unit": "serving"})
                st.success("Added to recipe draft.")
            with col_prev.expander("Preview"):
                st.write("Ingredients:", ", ".join(r.get("ingredients", [])))
                st.write("Allergens:", ", ".join(r.get("allergens", [])))
                st.json(r.get("nutrition", {}))

    st.divider()
    st.subheader("Build Recipe")
    recipe_name = st.text_input("Recipe Internal Name")
    recipe_consumer = st.text_input("Recipe Consumer-Facing Name")
    servings = st.number_input("Number of servings", min_value=1, value=1)

    if st.session_state.draft_items:
        st.write("Draft Items")
        new_items = []
        for idx, item in enumerate(st.session_state.draft_items):
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(item["name"])
            amount = c2.number_input("Amount", min_value=0.0, value=float(item.get("amount", 1)), step=0.25, key=f"draft_amt_{idx}")
            unit = c3.selectbox("Unit", UNITS, index=UNITS.index(item.get("unit", "serving")) if item.get("unit", "serving") in UNITS else 0, key=f"draft_unit_{idx}")
            new_items.append({"type": "product", "name": item["name"], "amount": amount, "unit": unit})
        st.session_state.draft_items = new_items

    if st.button("Save Recipe"):
        if not recipe_name:
            st.warning("Recipe name required.")
        elif not st.session_state.draft_items:
            st.warning("Add at least one item to recipe.")
        else:
            st.session_state.recipes.append({"name": recipe_name, "consumer_name": recipe_consumer or recipe_name, "servings": servings, "items": st.session_state.draft_items.copy()})
            st.session_state.draft_items = []
            st.success("Recipe saved.")

    if st.session_state.recipes:
        st.subheader("Saved Recipe Labels")
        selected_recipe = st.selectbox("Select saved recipe", [r["name"] for r in st.session_state.recipes])
        country = st.selectbox("Country format", ["UK / Natasha's Law Review", "US", "Canada"])
        rec = next(r for r in st.session_state.recipes if r["name"] == selected_recipe)
        label = label_text(rec, country)
        st.text_area("Label Preview", label, height=360)
        st.download_button("Download Label TXT", label, file_name=f"{selected_recipe}_label.txt", mime="text/plain")

with tab_menu:
    st.header("Create Menu")
    name = st.text_input("Menu Name")
    category = st.text_input("Category", placeholder="Breakfast, Entrees, Desserts")
    selected = st.multiselect("Recipes", [r["name"] for r in st.session_state.recipes])
    if st.button("Save Menu"):
        st.session_state.menus.append({"name": name, "category": category, "recipes": selected})
        st.success("Menu saved.")
    for m in st.session_state.menus:
        st.write(f"**{m['name']} - {m['category']}**: {', '.join(m['recipes'])}")

with tab_export:
    st.header("Export")
    st.download_button("Download Excel Workbook", excel_bytes(), file_name="food_intelligence_export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.info("This app is a preview. Label outputs are compliance review aids, not legal certification.")
