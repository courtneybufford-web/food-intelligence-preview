import streamlit as st
import re
import pandas as pd

st.set_page_config(page_title="Food Intelligence Preview", layout="wide")

st.title("Food Intelligence Platform — Preview MVP")

if "products" not in st.session_state:
    st.session_state.products = []

def parse_product(text, name):
    lower = text.lower()

    ingredients = []
    if "ingredients" in lower:
        part = lower.split("ingredients", 1)[1]
        part = part.split("nutrition", 1)[0]
        ingredients = [i.strip(" :.\n") for i in part.split(",") if i.strip()]

    allergens = []
    allergen_rules = {
        "wheat": "gluten",
        "milk": "dairy",
        "soy": "soy",
        "egg": "egg",
        "peanut": "peanut",
        "tree nut": "tree nuts",
        "almond": "tree nuts",
        "cashew": "tree nuts"
    }

    for word, allergen in allergen_rules.items():
        if word in lower:
            allergens.append(allergen)

    allergens = sorted(list(set(allergens)))

    def find(label):
        match = re.search(rf"{label}\D*(\d+)", lower)
        return int(match.group(1)) if match else 0

    return {
        "name": name,
        "ingredients": ingredients,
        "allergens": allergens,
        "nutrition": {
            "calories": find("calories"),
            "protein_g": find("protein"),
            "fat_g": find("fat"),
            "carbs_g": find("carbs"),
            "sodium_mg": find("sodium"),
        },
        "raw_text": text
    }

tab1, tab2, tab3 = st.tabs(["Add Product", "Search Products", "Recipe Builder"])

with tab1:
    st.header("Add Product Spec")

    product_name = st.text_input("Product Name", placeholder="Example: Wheat Dinner Roll")

    sample = """Ingredients: wheat flour, sugar, salt, soy lecithin
Nutrition: Calories 120 Protein 4g Fat 2g Carbs 24g Sodium 200mg"""

    text = st.text_area("Paste Product Specification Text", value=sample, height=180)

    if st.button("Parse and Save Product"):
        if not product_name:
            st.warning("Add a product name first.")
        else:
            product = parse_product(text, product_name)
            st.session_state.products.append(product)
            st.success(f"Saved {product_name}")
            st.json(product)

with tab2:
    st.header("Search Product Database")

    if not st.session_state.products:
        st.info("No products saved yet. Add one in the Add Product tab.")
    else:
        query = st.text_input("Search by ingredient or allergen", placeholder="wheat, dairy, soy, sodium")

        allergen_filter = st.multiselect(
            "Exclude allergens",
            ["gluten", "dairy", "soy", "egg", "peanut", "tree nuts"]
        )

        rows = []
        for p in st.session_state.products:
            searchable = " ".join(p["ingredients"] + p["allergens"]).lower()

            matches_query = not query or query.lower() in searchable
            excludes_allergens = not any(a in p["allergens"] for a in allergen_filter)

            if matches_query and excludes_allergens:
                rows.append({
                    "Name": p["name"],
                    "Ingredients": ", ".join(p["ingredients"]),
                    "Allergens": ", ".join(p["allergens"]) if p["allergens"] else "None",
                    "Calories": p["nutrition"]["calories"],
                    "Protein": p["nutrition"]["protein_g"],
                    "Sodium": p["nutrition"]["sodium_mg"]
                })

        st.dataframe(pd.DataFrame(rows), use_container_width=True)

with tab3:
    st.header("Recipe Builder")

    if not st.session_state.products:
        st.info("Add products first.")
    else:
        product_names = [p["name"] for p in st.session_state.products]
        selected = st.multiselect("Choose products for recipe", product_names)

        total = {
            "calories": 0,
            "protein_g": 0,
            "fat_g": 0,
            "carbs_g": 0,
            "sodium_mg": 0
        }

        allergens = set()

        for name in selected:
            product = next(p for p in st.session_state.products if p["name"] == name)
            qty = st.number_input(f"Quantity for {name}", min_value=1, value=1)

            for key in total:
                total[key] += product["nutrition"][key] * qty

            allergens.update(product["allergens"])

        if selected:
            st.subheader("Recipe Nutrition Total")
            st.json(total)

            if allergens:
                st.error("⚠️ Recipe allergens: " + ", ".join(sorted(allergens)))
            else:
                st.success("No allergens detected in recipe.")
