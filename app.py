import streamlit as st
import pandas as pd

st.set_page_config(page_title="Food Intelligence App", layout="wide")
st.title("Food Intelligence App")
st.caption("Stable rebuild: predictive database search formatted like ingredient search + recipe builder")

BADGES = {
    "Customer": "CUSTOMER",
    "Sample": "SAMPLE",
    "USDA": "USDA",
    "Open Food Facts": "OFF",
}

if "products" not in st.session_state:
    st.session_state.products = [
        {"name":"Chicken Roti-Bulk", "source":"Sample", "calories":37274, "protein":410, "fat":620, "carbs":2800, "salt":42, "allergens":"", "ingredients":"chicken thigh, spices, oil, garlic, onion", "serving_note":"37274 cal per Recipe yield"},
        {"name":"Harissa Chicken-Bulk", "source":"Sample", "calories":4372, "protein":360, "fat":190, "carbs":48, "salt":18, "allergens":"", "ingredients":"chicken, harissa paste, oil, garlic, lemon", "serving_note":"4372 cal per Recipe yield"},
        {"name":"Hot Honey Harissa Chicken-3oz portion", "source":"Sample", "calories":209, "protein":22, "fat":8, "carbs":10, "salt":0.9, "allergens":"", "ingredients":"chicken, honey, harissa paste, spices", "serving_note":"209 cal per Recipe yield"},
        {"name":"Chicken Roti Marinade", "source":"Sample", "calories":35665, "protein":12, "fat":3100, "carbs":120, "salt":64, "allergens":"mustard", "ingredients":"oil, lemon juice, garlic, mustard, spices", "serving_note":"35665 cal per Recipe yield"},
        {"name":"Chicken, broilers or fryers, thigh, meat only, cooked, roasted", "source":"USDA", "calories":251, "protein":25, "fat":16, "carbs":0, "salt":0.22, "allergens":"", "ingredients":"chicken thigh meat", "serving_note":"251 cal per cup, chopped or diced"},
        {"name":"Pacific Organic Low Sodium Chicken Broth", "source":"Open Food Facts", "calories":10, "protein":1, "fat":0, "carbs":1, "salt":0.24, "allergens":"", "ingredients":"chicken broth, chicken flavor, sea salt", "serving_note":"Pacific, 10 cal per 240 ml"},
        {"name":"Wheat Bun", "source":"Sample", "calories":140, "protein":5, "fat":2, "carbs":26, "salt":0.55, "allergens":"cereals containing gluten", "ingredients":"wheat flour, water, yeast, salt", "serving_note":"140 cal per bun"},
        {"name":"Cheddar Cheese", "source":"Sample", "calories":113, "protein":7, "fat":9, "carbs":1, "salt":0.18, "allergens":"milk", "ingredients":"milk, salt, cultures, enzymes", "serving_note":"113 cal per slice"},
    ]

if "recipe_items" not in st.session_state:
    st.session_state.recipe_items = []

if "saved_recipes" not in st.session_state:
    st.session_state.saved_recipes = []


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
    # simple predictive matching: all typed words must appear somewhere
    words = [w for w in q.split() if w]
    if words and all(w in haystack for w in words):
        return 35
    return 0


def search_products(query):
    if not query:
        return st.session_state.products[:8]
    scored = []
    for p in st.session_state.products:
        score = prediction_score(p, query)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (x[0], float(x[1].get("calories", 0))), reverse=True)
    return [p for _, p in scored]


def product_table(products):
    return pd.DataFrame(products)


def badge_html(source):
    label = BADGES.get(source, source.upper() if source else "SOURCE")
    return f"<span style='font-size:11px; padding:2px 7px; border:1px solid #d8d2a8; border-radius:8px; background:#fbf7df; color:#776b22; font-weight:700;'>{label}</span>"


def render_search_result(product, index, prefix="search"):
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
            st.markdown(
                f"**{product['name']}** &nbsp; {badge_html(product.get('source', 'Customer'))}",
                unsafe_allow_html=True,
            )
            note = product.get("serving_note") or f"{product.get('calories', 0)} cal per serving"
            st.caption(note)
            if product.get("allergens"):
                st.warning(f"Allergens: {product.get('allergens')}")

        with action_col:
            if st.button("+ Add to Recipe", key=f"{prefix}_add_{index}_{product['name']}"):
                item = dict(product)
                item["qty"] = 1.0
                st.session_state.recipe_items.append(item)
                st.success(f"Added {product['name']}")

        with preview_col:
            with st.expander("Preview"):
                st.write("**Ingredients**")
                st.write(product.get("ingredients", ""))
                st.write("**Allergens**")
                st.write(product.get("allergens", "") or "none")
                st.write("**Nutrition**")
                st.json({
                    "calories": product.get("calories", 0),
                    "protein_g": product.get("protein", 0),
                    "fat_g": product.get("fat", 0),
                    "carbs_g": product.get("carbs", 0),
                    "salt_g": product.get("salt", 0),
                })


tabs = st.tabs(["Dashboard", "Add Product", "Recipe Builder", "Saved Recipes"])

with tabs[0]:
    st.header("Dashboard")
    c1, c2, c3 = st.columns(3)
    c1.metric("Products", len(st.session_state.products))
    c2.metric("Recipe Items", len(st.session_state.recipe_items))
    c3.metric("Saved Recipes", len(st.session_state.saved_recipes))
    st.subheader("Customer Database")
    st.dataframe(product_table(st.session_state.products), use_container_width=True)

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
            st.session_state.products.append({
                "name": name,
                "source": "Customer",
                "calories": calories,
                "protein": protein,
                "fat": fat,
                "carbs": carbs,
                "salt": salt,
                "allergens": allergens,
                "ingredients": ingredients,
                "serving_note": serving_note or f"{calories} cal per serving",
            })
            st.success("Saved")
        else:
            st.warning("Add a name first")

with tabs[2]:
    st.header("Recipe Builder")

    st.subheader("Database Search")
    st.caption("Start typing to preview predicted matches. No search button needed.")
    q = st.text_input(
        "Search ingredients/products",
        placeholder="Type chicken, bun, cheese, flour...",
        label_visibility="collapsed",
    )
    results = search_products(q)

    if q and not results:
        st.info("No matching products found. Add it in the Add Product tab.")
    else:
        if q:
            st.caption(f"Showing predicted matches for: {q}")
        else:
            st.caption("Suggested database items")
        for i, p in enumerate(results[:12]):
            render_search_result(p, i, prefix="predictive")

    st.divider()
    st.subheader("Current Recipe Items")

    if not st.session_state.recipe_items:
        st.info("Use Database Search above to add items to your recipe.")
    else:
        for idx, item in enumerate(st.session_state.recipe_items):
            c1, c2, c3 = st.columns([5, 2, 1])
            c1.write(item["name"])
            st.session_state.recipe_items[idx]["qty"] = c2.number_input(
                "Qty", min_value=0.0, value=float(item.get("qty", 1)), step=0.25, key=f"qty_{idx}"
            )
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
                st.session_state.saved_recipes.append({
                    "name": recipe_name,
                    "servings": servings,
                    "items": list(st.session_state.recipe_items),
                    "label": label,
                    "nutrition_per_serving": per,
                })
                st.success("Recipe saved")
            else:
                st.warning("Add a recipe name")

with tabs[3]:
    st.header("Saved Recipes")
    if not st.session_state.saved_recipes:
        st.info("No saved recipes yet")
    else:
        for r in st.session_state.saved_recipes:
            with st.expander(r["name"]):
                st.text_area("Label", r["label"], height=220)
                st.download_button("Download label text", r["label"], file_name=f"{r['name']}_label.txt")
