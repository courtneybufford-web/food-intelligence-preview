import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title='Food Intelligence MVP', layout='wide')
st.title('Food Intelligence MVP')

if 'products' not in st.session_state:
    st.session_state.products = []
if 'recipe' not in st.session_state:
    st.session_state.recipe = []

UNITS = ['g','kg','mg','oz','lb','ml','l','tsp','tbsp','cup','each','slice','serving']

ALLERGEN_KEYWORDS = {
    'gluten': ['wheat','barley','rye','oats','gluten'],
    'milk': ['milk','cheese','butter','cream','whey','casein'],
    'egg': ['egg'],
    'soy': ['soy','soya'],
    'peanut': ['peanut'],
    'tree nuts': ['almond','cashew','walnut','pecan','hazelnut','pistachio'],
    'fish': ['fish'],
    'shellfish': ['shrimp','crab','lobster','prawn'],
    'sesame': ['sesame']
}

def number_after(label, text):
    m = re.search(rf'{label}[^0-9]*(\d+(?:\.\d+)?)', text, re.I)
    return float(m.group(1)) if m else 0.0

def parse_product(text):
    lower = text.lower()
    ingredients = []
    if 'ingredients' in lower:
        part = lower.split('ingredients', 1)[1]
        if 'nutrition' in part:
            part = part.split('nutrition', 1)[0]
        ingredients = [x.strip(' :.\n') for x in part.split(',') if x.strip(' :.\n')]

    allergens = []
    haystack = lower + ' ' + ' '.join(ingredients)
    for allergen, words in ALLERGEN_KEYWORDS.items():
        if any(w in haystack for w in words):
            allergens.append(allergen)

    sodium = number_after('sodium', lower)
    nutrition = {
        'calories': number_after('calories', lower),
        'fat_g': number_after('fat', lower),
        'saturated_fat_g': number_after('saturated fat|saturates', lower),
        'carbs_g': number_after('carbohydrate|carbs', lower),
        'sugars_g': number_after('sugars|sugar', lower),
        'protein_g': number_after('protein', lower),
        'sodium_mg': sodium,
        'salt_g': round(sodium * 2.5 / 1000, 3) if sodium else number_after('salt', lower),
    }
    return ingredients, sorted(set(allergens)), nutrition

def product_df():
    rows=[]
    for i,p in enumerate(st.session_state.products):
        rows.append({
            'ID': i,
            'Name': p['name'],
            'Source': p.get('source','Customer'),
            'Ingredients': ', '.join(p['ingredients']),
            'Allergens': ', '.join(p['allergens']),
            **p['nutrition']
        })
    return pd.DataFrame(rows)

def recipe_totals():
    total = {'calories':0,'fat_g':0,'saturated_fat_g':0,'carbs_g':0,'sugars_g':0,'protein_g':0,'sodium_mg':0,'salt_g':0}
    allergens=set()
    for item in st.session_state.recipe:
        p = st.session_state.products[item['product_id']]
        qty = item['qty']
        for k in total:
            total[k] += p['nutrition'].get(k,0) * qty
        allergens.update(p['allergens'])
    return total, sorted(allergens)

def label_text(name, servings):
    total, allergens = recipe_totals()
    per = {k: round(v / max(servings,1), 3) for k,v in total.items()}
    ingredient_list = ', '.join([st.session_state.products[i['product_id']]['name'] for i in st.session_state.recipe])
    return f'''{name}\n\nIngredients: {ingredient_list}\n\nAllergens: {', '.join(allergens) if allergens else 'None detected'}\n\nNutrition per serving:\nEnergy: {per['calories']} kcal\nFat: {per['fat_g']} g\nSaturates: {per['saturated_fat_g']} g\nCarbohydrate: {per['carbs_g']} g\nSugars: {per['sugars_g']} g\nProtein: {per['protein_g']} g\nSalt: {per['salt_g']} g\n'''

tab1, tab2, tab3, tab4 = st.tabs(['Add Product','Database Search','Recipe Builder','Export'])

with tab1:
    st.header('Add Product')
    name = st.text_input('Product name')
    spec = st.text_area('Paste spec text', 'Ingredients: wheat flour, sugar, salt, soy lecithin\nNutrition: Calories 120 Fat 2g Saturated Fat 1g Carbs 24g Sugars 5g Protein 4g Sodium 200mg')
    if st.button('Save product'):
        if not name:
            st.warning('Enter a product name')
        else:
            ingredients, allergens, nutrition = parse_product(spec)
            st.session_state.products.append({'name':name,'ingredients':ingredients,'allergens':allergens,'nutrition':nutrition,'source':'Customer'})
            st.success('Saved')
            st.json(st.session_state.products[-1])

with tab2:
    st.header('Database Search')
    q = st.text_input('Search products', placeholder='chicken, flour, milk...')
    if st.session_state.products:
        df = product_df()
        if q:
            mask = df.astype(str).apply(lambda row: row.str.contains(q, case=False, regex=False).any(), axis=1)
            df = df[mask]
        st.dataframe(df, use_container_width=True)
    else:
        st.info('Add products first.')

with tab3:
    st.header('Recipe Builder')
    if not st.session_state.products:
        st.info('Add products first.')
    else:
        product_names = [p['name'] for p in st.session_state.products]
        selected = st.selectbox('Choose product to add', product_names)
        qty = st.number_input('Amount / quantity multiplier', min_value=0.0, value=1.0, step=0.25)
        unit = st.selectbox('Unit', UNITS)
        if st.button('Add to recipe'):
            idx = product_names.index(selected)
            st.session_state.recipe.append({'product_id':idx,'qty':qty,'unit':unit})
            st.success('Added to recipe')
        if st.session_state.recipe:
            st.subheader('Current Recipe')
            rows=[]
            for item in st.session_state.recipe:
                rows.append({'Product': st.session_state.products[item['product_id']]['name'], 'Amount': item['qty'], 'Unit': item['unit']})
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            recipe_name = st.text_input('Recipe name', 'My Recipe')
            servings = st.number_input('Number of servings', min_value=1, value=1)
            st.text_area('Label preview', label_text(recipe_name, servings), height=300)
            if st.button('Clear recipe'):
                st.session_state.recipe = []
                st.rerun()

with tab4:
    st.header('Export')
    if st.session_state.products:
        csv = product_df().to_csv(index=False)
        st.download_button('Download product CSV', csv, 'products.csv', 'text/csv')
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            product_df().to_excel(writer, index=False, sheet_name='Products')
        st.download_button('Download Excel', output.getvalue(), 'products.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        st.info('No products to export.')
