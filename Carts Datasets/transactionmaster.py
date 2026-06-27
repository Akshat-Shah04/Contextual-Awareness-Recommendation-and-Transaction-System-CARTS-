import random
import pandas as pd

# List of items commonly bought in Indian grocery stores
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


# Function to create a single transaction with 5 to 10 items
def generate_transaction():
    num_items = random.randint(5, 12)
    return random.sample(items, num_items)


# Generate 9453 transactions
transactions = [generate_transaction() for _ in range(9453)]

# Find the maximum number of items in any transaction to define columns
max_items = max(len(t) for t in transactions)
column_names = [f"item{i+1}" for i in range(max_items)]

# Convert to DataFrame and fill missing values with None
df_transactions = pd.DataFrame(
    [t + [None] * (max_items - len(t)) for t in transactions], columns=column_names
)

# Save CSV
df_transactions.to_csv(
    "C:/Users/pathi/Desktop/akshat/sem 7/Minor Project/Carts Datasets/indian_grocery_transactions.csv",
    index=False,
)

df_transactions.head()
