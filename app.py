import streamlit as st

st.set_page_config(layout="wide")

# -----------------------------
# UNIT CONVERSION (TO GRAMS)
# -----------------------------
UNIT_TO_G = {
    "g": 1,
    "kg": 1000,
    "oz": 28.35,
    "lb": 453.6
}

def to_grams(qty, unit):
    return qty * UNIT_TO_G.get(unit, 0)

# -----------------------------
# SAMPLE INGREDIENT DATABASE
# -----------------------------
DATABASE = [
    {"name": "Chicken Breast", "nutrition": {"calories": 1.65, "protein": 0.31, "fat": 0.036}},
    {"name": "Olive Oil", "nutrition": {"calories": 8.84, "fat": 1}},
    {"name": "Flour", "nutrition": {"calories": 3.64, "carbs": 0.76}},
]

# -----------------------------
# INIT STATE
# -----------------------------
if "recipe" not in st.session_state:
    st.session_state.recipe = []

# -----------------------------
# SEARCH
# -----------------------------
query = st.text_input("Search ingredients")

results = [x for x in DATABASE if query.lower() in x["name"].lower()] if query else []

if results:
    selected = st.selectbox("Select ingredient", [r["name"] for r in results])

    if st.button("Add Ingredient"):
        ingredient = next(r for r in results if r["name"] == selected)
        st.session_state.recipe.append({
            "name": ingredient["name"],
            "quantity": 100,
            "unit": "g",
            "waste": 0,
            "nutrition": ingredient["nutrition"]
        })

# -----------------------------
# RECIPE TABLE
# -----------------------------
st.subheader("Recipe Builder")

updated_recipe = []

for i, item in enumerate(st.session_state.recipe):
    col1, col2, col3, col4, col5 = st.columns([2,1,1,1,1])

    name = col1.write(item["name"])
    qty = col2.number_input(f"Qty {i}", value=item["quantity"], key=f"qty{i}")
    unit = col3.selectbox(f"Unit {i}", ["g","kg","oz","lb"], key=f"unit{i}")
    waste = col4.number_input(f"Waste % {i}", value=item["waste"], key=f"waste{i}")
    delete = col5.checkbox("X", key=f"del{i}")

    if not delete:
        grams = to_grams(qty, unit)
        grams *= (1 - waste/100)

        updated_recipe.append({
            **item,
            "quantity": qty,
            "unit": unit,
            "waste": waste,
            "grams": grams
        })

st.session_state.recipe = updated_recipe

# -----------------------------
# CALCULATIONS (NEW ENGINE)
# -----------------------------
total_weight = sum(x["grams"] for x in st.session_state.recipe) if st.session_state.recipe else 0

total_nutrition = {}

for item in st.session_state.recipe:
    for k, v in item["nutrition"].items():
        total_nutrition[k] = total_nutrition.get(k, 0) + v * item["grams"]

# -----------------------------
# SERVING OPTIONS
# -----------------------------
st.subheader("Serving Settings")

mode = st.selectbox("Serving Mode", ["Per Serving", "Per 100g", "Custom Weight", "Full Recipe"])

servings = st.number_input("Servings", 1, 100, 4)

custom_weight = None
if mode == "Custom Weight":
    custom_weight = st.number_input("Serving Weight (g)", 1.0, 1000.0, 100.0)

# -----------------------------
# SERVING CALCULATION
# -----------------------------
def calculate_serving():
    if total_weight == 0:
        return total_nutrition

    per_g = {k: v / total_weight for k, v in total_nutrition.items()}

    if mode == "Per Serving":
        weight = total_weight / servings
    elif mode == "Per 100g":
        weight = 100
    elif mode == "Custom Weight":
        weight = custom_weight
    else:
        return total_nutrition

    return {k: v * weight for k, v in per_g.items()}

panel = calculate_serving()

# -----------------------------
# DISPLAY PANEL (LIVE UPDATE)
# -----------------------------
st.subheader("Nutrition Facts Panel")

st.write(f"Calories: {int(panel.get('calories',0))}")
st.write(f"Protein: {round(panel.get('protein',0),1)} g")
st.write(f"Fat: {round(panel.get('fat',0),1)} g")
st.write(f"Carbs: {round(panel.get('carbs',0),1)} g")
