import pandas as pd
from pathlib import Path
from utils.cleaner import clean_dataframe
from utils.exporter import format_excel_sheet

out_dir = Path('output')

dfs = []
for p in sorted(out_dir.glob('*.csv')):
    if p.name in ['Haircare_Leads.csv', 'Skincare_Leads.csv', 'Herbal_Leads.csv']:
        continue
    try:
        df = pd.read_csv(p)
        dfs.append(df)
        print(f"Loaded {p.name}: {len(df)} rows")
    except Exception as e:
        print(f"Error loading {p.name}: {e}")

combined = pd.concat(dfs, ignore_index=True)
cleaned = clean_dataframe(combined.to_dict(orient='records'))

print("\n--- Total Combined Dataset Summary ---")
print("Total rows:", len(cleaned))
print("Marketplaces:\n", cleaned['Marketplace'].value_counts())
print("Categories:\n", cleaned['Product Category'].value_counts())

categories = [
    ('Haircare', 'Haircare_Leads.xlsx', 'Haircare_Leads.csv', 'Haircare Leads'),
    ('Skincare', 'Skincare_Leads.xlsx', 'Skincare_Leads.csv', 'Skincare Leads'),
    ('Herbal', 'Herbal_Leads.xlsx', 'Herbal_Leads.csv', 'Herbal Leads')
]

for cat, xlsx_name, csv_name, sheet_name in categories:
    sub_df = cleaned[cleaned['Product Category'] == cat].copy().reset_index(drop=True)
    
    # Save CSV
    csv_path = out_dir / csv_name
    sub_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    # Save Excel (with fallback if user has file open in Excel)
    xlsx_path = out_dir / xlsx_name
    try:
        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
            sub_df.to_excel(writer, index=False, sheet_name=sheet_name)
            format_excel_sheet(writer.sheets[sheet_name], sub_df)
    except PermissionError:
        fallback_path = out_dir / f"{xlsx_path.stem}_Updated.xlsx"
        with pd.ExcelWriter(fallback_path, engine='openpyxl') as writer:
            sub_df.to_excel(writer, index=False, sheet_name=sheet_name)
            format_excel_sheet(writer.sheets[sheet_name], sub_df)
        xlsx_name = fallback_path.name
        
    ajio_count = (sub_df['Marketplace'] == 'Ajio').sum()
    ei_count = (sub_df['Marketplace'] == 'ExportersIndia').sum()
    print(f"\nExported {xlsx_name}: {len(sub_df)} leads (Ajio: {ajio_count}, ExportersIndia: {ei_count})")

print("\nAll 3 category Excel workbooks updated successfully with Ajio + ExportersIndia data!")
