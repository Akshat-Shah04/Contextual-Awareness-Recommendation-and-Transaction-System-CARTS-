x`import pandas as pd


def extract_items_to_excel(csv_file, output_file="items.xlsx"):
    """
    Extract unique item names from ALL columns of a CSV dataset,
    count how many times each item appears, and save them into an Excel file.

    :param csv_file: Path to input CSV file
    :param output_file: Path for the output Excel file
    """
    # Read the CSV file
    df = pd.read_csv(csv_file)

    # Flatten all values into one series (all rows + all columns)
    items = pd.Series(df.values.ravel()).dropna().astype(str)

    # Clean and standardize items
    items = items.str.strip()  # remove extra spaces
    items = items[items != ""]  # drop empty strings
    items = items.str.title()  # normalize case (e.g., 'milk', 'Milk' -> 'Milk')

    # Count item frequencies
    item_counts = items.value_counts().reset_index()
    item_counts.columns = ["Item Names", "Total"]

    # Sort alphabetically by item name
    item_counts = item_counts.sort_values(
        by="Item Names", key=lambda x: x.str.lower()
    ).reset_index(drop=True)

    # Save to Excel
    item_counts.to_excel(output_file, index=False)

    print(
        f"Extracted {len(item_counts)} unique items and saved to '{output_file}' with counts"
    )


# Example usage
if __name__ == "__main__":
    extract_items_to_excel(
        r"C:\Users\pathi\Desktop\akshat\sem 7\Minor Project\Carts Datasets\TransactionDatasetNew.csv",
        output_file="unique_items1.xlsx",
    )
