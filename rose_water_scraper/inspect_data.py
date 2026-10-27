import pandas as pd
from pathlib import Path

out_dir = Path("output")
lead_files = ["Haircare_Leads.csv", "Skincare_Leads.csv", "Herbal_Leads.csv"]

for filename in lead_files:
    file_path = out_dir / filename
    if not file_path.exists():
        continue
    df = pd.read_csv(file_path)
    print("=" * 50)
    print(f"File: {filename}")
    print(f"Total Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    print(f"Marketplace distribution:\n{df['Marketplace'].value_counts().to_dict()}")
    print(f"Unique Brands: {df['Brand Name'].nunique()}")
    print(f"Unique Keywords: {df['Keyword'].nunique()} ({list(df['Keyword'].unique()[:6])})")
    print(f"Rows with Email: {len(df[df['Contact Email'].fillna('').str.strip() != ''])}")
    print(f"Rows with Phone: {len(df[df['Phone Number'].fillna('').str.strip() != ''])}")
    print(f"Rows with Website: {len(df[df['Seller/Brand Website'].fillna('').str.strip() != ''])}")
    print(f"Rows with LinkedIn: {len(df[df['LinkedIn'].fillna('').str.strip() != ''])}")
    print("\nSample records:")
    for idx, row in df.head(3).iterrows():
        print(f"  [{row['Marketplace']}] {row['Brand Name']} | {row['Product Name'][:40]} | Phone: {row['Phone Number']} | Site: {row['Seller/Brand Website']}")
    print()
