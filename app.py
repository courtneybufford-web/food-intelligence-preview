import streamlit as st
import pandas as pd

st.set_page_config(page_title="Food Intelligence App", layout="wide")
st.title("Food Intelligence App")
st.caption("Stable rebuild: product search + recipe builder + label preview")

if "products" not in st.session_state:
    st.session_state.products = [
        {"name":"Chicken Breast", "source":"Sample", "calories":165, "protein":31, "fat":3.6, "carbs":0, "salt":0.18, "allergens":"", "ingredients":"chicken breast"},
        {"name":"Wheat Bun", "source":"Sample", "calories":140, "protein":5, "fat":2, "carbs":26, "salt":0.55, "allergens":"cereals containing gluten", "ingredients":"wheat flour, water, yeast, salt"},
        {"name":"Cheddar Cheese", "source":"Sample", "calories":113, "protein":7, "fat":9, "carbs":1, "salt":0.18, "allergens":"milk", "ingredients":"milk, salt, cultures, enzymes"},
    ]

if "recipe_items" not in st.session_state:
    st.session_state.recipe_items = []

if "saved_recipes" not in st.session_state:
    st.session_state.saved_recipes = []

def product_df(items):
    return pd.DataFrame(items)

def totals(items):
    t = {"calories":0.0,"protein":0.0,"fat":0.0,"carbs":0.0,"salt":0.0}
    allergens = set()
    ingredients = []
    for item in items:
        qty = float(item.get("qty",1))
        for k in t:
            t[k] += float(item.get(k,0))*qty
        if item.get("allergens"):
            for a in str(item["allergens"]).split(","):
                if a.strip(): allergens.add(a.strip())
        if item.get("ingredients"):
            ingredients.append(item["ingredients"])
    return t, sorted(allergens), ", ".join(ingredients)

tabs = st.tabs(["Database Search", "Add Product", "Recipe Builder", "Saved Recipes"])

with tabs[0]:
    st.header("Database Search")
    q = st.text_input("Search products", placeholder="Try chicken, bun, cheese")
    results = st.session_state.products
    if q:
        results = [p for p in st.session_state.products if q.lower() in str(p).lower()]
    for i, p in enumerate(results):
        c1, c2, c3 = st.columns([5,2,2])
        with c1:
            st.markdown(f"**{p['name']}**")
            st.caption(f"{p['calories']} kcal | source: {p.get('source','Customer')} | allergens: {p.get('allergens','') or 'none'}")
        with c2:
            if st.button("Add to Recipe", key=f"add_{i}_{p['name']}"):
                item = dict(p)
                item["qty"] = 1
                st.session_state.recipe_items.append(item)
                st.success(f"Added {p['name']}")
        with c3:
            with st.expander("Preview"):
                st.write(p)

with tabs[1]:
    st.header("Add Customer Product / Ingredient")
    name = st.text_input("Product name")
    ingredients = st.text_area("Ingredients")
    allergens = st.text_input("Allergens", placeholder="milk, cereals containing gluten")
    c1,c2,c3,c4,c5 = st.columns(5)
    calories = c1.number_input("Calories", min_value=0.0, value=0.0)
    protein = c2.number_input("Protein g", min_value=0.0, value=0.0)
    fat = c3.number_input("Fat g", min_value=0.0, value=0.0)
    carbs = c4.number_input("Carbs g", min_value=0.0, value=0.0)
    salt = c5.number_input("Salt g", min_value=0.0, value=0.0)
    if st.button("Save Product"):
        if name:
            st.session_state.products.append({"name":name,"source":"Customer","calories":calories,"protein":protein,"fat":fat,"carbs":carbs,"salt":salt,"allergens":allergens,"ingredients":ingredients})
            st.success("Saved")
        else:
            st.warning("Add a name first")

with tabs[2]:
    st.header("Recipe Builder")
    if not st.session_state.recipe_items:
        st.info("Add items from Database Search first.")
    else:
        for idx, item in enumerate(st.session_state.recipe_items):
            c1,c2,c3 = st.columns([5,2,1])
            c1.write(item["name"])
            st.session_state.recipe_items[idx]["qty"] = c2.number_input("Qty", min_value=0.0, value=float(item.get("qty",1)), step=0.25, key=f"qty_{idx}")
            if c3.button("Remove", key=f"rem_{idx}"):
                st.session_state.recipe_items.pop(idx)
                st.rerun()
        recipe_name = st.text_input("Recipe name")
        servings = st.number_input("Servings", min_value=1, value=1)
        total, allergens, ingredient_list = totals(st.session_state.recipe_items)
        per = {k: round(v/servings,2) for k,v in total.items()}
        st.subheader("Nutrition per serving")
        st.json(per)
        st.subheader("Ingredient statement")
        st.text_area("Ingredient list", ingredient_list, height=100)
        st.subheader("Allergen declaration")
        st.text_area("Allergens", "Contains: " + (", ".join(allergens) if allergens else "No declarable allergens detected"), height=80)
        st.subheader("UK-style label draft")
        label = f"""{recipe_name or 'Recipe'}\n\nIngredients: {ingredient_list}\n\nContains: {', '.join(allergens) if allergens else 'No declarable allergens detected'}\n\nNutrition per serving:\nEnergy: {per['calories']} kcal\nFat: {per['fat']} g\nCarbohydrate: {per['carbs']} g\nProtein: {per['protein']} g\nSalt: {per['salt']} g\n"""
        st.text_area("Label preview", label, height=260)
        if st.button("Save Recipe"):
            if recipe_name:
                st.session_state.saved_recipes.append({"name":recipe_name,"servings":servings,"items":list(st.session_state.recipe_items),"label":label,"nutrition_per_serving":per})
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
