import random
import pandas as pd

items = [
    "Tomato",
    "Bell Peppers",
    "Onions",
    "Potato",
    "Paneer",
    "Milk",
    "Curd",
    "Coriander",
    "Lemon",
    "Ginger",
    "Garlic",
    "Green Chili",
    "Tea Powder",
    "Coffee Powder",
    "Coconut",
    "Okra",
    "Spinach",
    "Cabbage",
    "Carrot",
    "Beetroot",
    "Cauliflower",
    "Brinjal",
    "Capsicum",
    "Chili Powder",
    "Turmeric Powder",
    "Rice",
    "Wheat Flour",
    "Sugar",
    "Salt",
    "Cooking Oil",
    "Mustard Seeds",
    "Cumin Seeds",
    "Dals",
    "Sooji",
    "Semolina",
    "Besan",
    "Yogurt",
    "Lassi",
    "Butter",
    "Cheese",
    "Bread",
    "Biscuits",
    "Jam",
    "Honey",
    "Pickle",
    "Tamarind",
    "Fenugreek Leaves",
    "Mint Leaves",
    "Pomegranate",
    "Banana",
    "Apple",
    "Mango",
    "Orange",
    "Papaya",
    "Guava",
]

# Assign categories
categories = {
    "Vegetables": [
        "Tomato",
        "Bell Peppers",
        "Onions",
        "Potato",
        "Coriander",
        "Ginger",
        "Garlic",
        "Green Chili",
        "Okra",
        "Spinach",
        "Cabbage",
        "Carrot",
        "Beetroot",
        "Cauliflower",
        "Brinjal",
        "Capsicum",
        "Fenugreek Leaves",
        "Mint Leaves",
        "Lemon",
    ],
    "Fruits": [
        "Pomegranate",
        "Banana",
        "Apple",
        "Mango",
        "Orange",
        "Papaya",
        "Guava",
        "Coconut",
    ],
    "Dairy": ["Paneer", "Milk", "Curd", "Yogurt", "Lassi", "Butter", "Cheese"],
    "Staples": [
        "Rice",
        "Wheat Flour",
        "Sugar",
        "Salt",
        "Cooking Oil",
        "Dals",
        "Sooji",
        "Semolina",
        "Besan",
        "Bread",
    ],
    "Spices": [
        "Chili Powder",
        "Turmeric Powder",
        "Mustard Seeds",
        "Cumin Seeds",
        "Tea Powder",
        "Coffee Powder",
        "Tamarind",
    ],
    "Others": ["Biscuits", "Jam", "Honey", "Pickle"],
}

quantity_units = {
    "Tomato": "1kg",
    "Bell Peppers": "500g",
    "Onions": "1kg",
    "Potato": "1kg",
    "Paneer": "200g",
    "Milk": "1L",
    "Curd": "500g",
    "Coriander": "50g",
    "Lemon": "250g",
    "Ginger": "100g",
    "Garlic": "100g",
    "Green Chili": "100g",
    "Tea Powder": "100g",
    "Coffee Powder": "100g",
    "Coconut": "1pc",
    "Okra": "500g",
    "Spinach": "250g",
    "Cabbage": "1pc",
    "Carrot": "500g",
    "Beetroot": "500g",
    "Cauliflower": "1pc",
    "Brinjal": "500g",
    "Capsicum": "500g",
    "Chili Powder": "100g",
    "Turmeric Powder": "100g",
    "Rice": "1kg",
    "Wheat Flour": "1kg",
    "Sugar": "1kg",
    "Salt": "1kg",
    "Cooking Oil": "1L",
    "Mustard Seeds": "100g",
    "Cumin Seeds": "100g",
    "Dals": "1kg",
    "Sooji": "1kg",
    "Semolina": "1kg",
    "Besan": "500g",
    "Yogurt": "500g",
    "Lassi": "500ml",
    "Butter": "200g",
    "Cheese": "200g",
    "Bread": "1loaf",
    "Biscuits": "200g",
    "Jam": "250g",
    "Honey": "250g",
    "Pickle": "250g",
    "Tamarind": "100g",
    "Fenugreek Leaves": "50g",
    "Mint Leaves": "50g",
    "Pomegranate": "1pc",
    "Banana": "1dozen",
    "Apple": "1kg",
    "Mango": "1kg",
    "Orange": "1kg",
    "Papaya": "1pc",
    "Guava": "1kg",
}

data = []

for item in items:
    # Determine category
    for cat, cat_items in categories.items():
        if item in cat_items:
            category = cat
            break

    # Set CP ranges by category
    if category == "Vegetables":
        cp = round(random.uniform(20, 80), 2)
        profit_range = (5, 15)
    elif category == "Fruits":
        cp = round(random.uniform(40, 150), 2)
        profit_range = (8, 20)
    elif category == "Dairy":
        cp = round(random.uniform(40, 250), 2)
        profit_range = (10, 20)
    elif category == "Staples":
        cp = round(random.uniform(40, 200), 2)
        profit_range = (5, 15)
    elif category == "Spices":
        cp = round(random.uniform(50, 300), 2)
        profit_range = (10, 25)
    else:  # Others
        cp = round(random.uniform(50, 300), 2)
        profit_range = (10, 20)

    # Determine if sold at profit or loss
    if random.random() < 0.90:
        profit_percent = round(random.uniform(*profit_range), 2)
        sp = round(cp * (1 + profit_percent / 100), 2)
        loss = 0
        loss_percent = 0
    else:
        loss_percent = round(random.uniform(5, 20), 2)
        sp = round(cp * (1 - loss_percent / 100), 2)
        profit_percent = 0
        loss = round(cp - sp, 2)

    profit = round(sp - cp if sp >= cp else 0, 2)
    margin = profit
    margin_percent = profit_percent

    data.append(
        {
            "Item Name": item,
            "Category": category,
            "Quantity": quantity_units.get(item, "1unit"),
            "CP (Rs)": cp,
            "SP (Rs)": sp,
            "Profit (Rs)": profit,
            "Profit (%)": profit_percent,
            "Margin (Rs)": margin,
            "Margin (%)": margin_percent,
            "Loss (Rs)": loss,
            "Loss (%)": loss_percent,
        }
    )

df_items = pd.DataFrame(data)

# Save CSV
df_items.to_csv(
    "C:/Users/pathi/Desktop/akshat/sem 7/Minor Project/Carts Datasets/indian_grocery_item_master.csv",
    index=False,
)

df_items.head()
