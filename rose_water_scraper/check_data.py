import pandas as pd

df = pd.read_csv('output/multi_3_keywords_all_20261003_184545.csv')
print("Total rows:", len(df))
print("Columns:", list(df.columns))
src_counts = df['Source'].value_counts().to_dict()
print("Source distribution:", src_counts)
print("Rows with Email:", df['Email'].notna().sum())
print("Rows with Contact:", df['Contact'].notna().sum())
print("Unique Companies:", df['Company'].nunique())
print()
print("Sample URLs by source:")
for src in df['Source'].unique():
    grp = df[df['Source'] == src]
    url = grp['URL'].iloc[0]
    print(f"  [{src}] {url}")
