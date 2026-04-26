import streamlit as st
import re

st.title("Food Intelligence Platform (Preview MVP)")

input_text = st.text_area("Paste Food Product Spec Text")

def parse_product(text):
    text = text.lower()

    ingredients = []
    if "ingredients" in text:
        ing_part = text.split("ingredients")[1]
        ingredients = [i.strip() for i in ing_part.split(",")]

    allergens = []
    if "wheat" in text:
        allergens.append("gluten")
    if "milk" in text:
        allergens.append("dairy")
    if "soy" in text:
        allergens.append("soy")

    def find(label):
        match = re.search(rf"{label}\D*(\d+)", text)
        return int(match.group(1)) if match else 0

    nutrition = {
        "calories": find("calories"),
        "protein": find("protein"),
        "fat": find("fat"),
        "carbs": find("carbs"),
        "sodium": find("sodium"),
    }

    return {
        "ingredients": ingredients,
        "allergens": allergens,
        "nutrition": nutrition
    }

if st.button("Parse Product"):
    result = parse_product(input_text)

    st.subheader("Output")
    st.json(result)

    if result["allergens"]:
        st.error("⚠️ Allergens detected: " + ", ".join(result["allergens"]))
    else:
        st.success("No allergens detected")
