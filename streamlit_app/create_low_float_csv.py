#!/usr/bin/env python3
"""
Create a CSV of low float stocks (float < 500M shares)
"""
import pandas as pd

# Read the complete stocks file
print("Reading all_stocks_complete.csv...")
df = pd.read_csv('all_stocks_complete.csv')

print(f"Total stocks: {len(df)}")

# Filter for float < 500M
low_float = df[df['float_shares'] < 500_000_000].copy()

print(f"Stocks with float < 500M: {len(low_float)}")

# Sort by float (lowest first)
low_float = low_float.sort_values('float_shares')

# Save to new CSV
output_file = 'low_float_stocks.csv'
low_float.to_csv(output_file, index=False)

print(f"\n✓ Saved to {output_file}")
print(f"\nFloat range:")
print(f"  Lowest: {low_float['float_shares'].min():,.0f} shares")
print(f"  Highest: {low_float['float_shares'].max():,.0f} shares")
print(f"  Median: {low_float['float_shares'].median():,.0f} shares")
