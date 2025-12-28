#!/usr/bin/env python3
"""
Create a CSV of ultra low float stocks (float < 50M shares)
"""
import pandas as pd

# Read the complete stocks file
print("Reading all_stocks_complete.csv...")
df = pd.read_csv('all_stocks_complete.csv')

print(f"Total stocks: {len(df)}")

# Filter for float < 50M
ultra_low_float = df[df['float_shares'] < 50_000_000].copy()

print(f"Stocks with float < 50M: {len(ultra_low_float)}")

# Sort by float (lowest first)
ultra_low_float = ultra_low_float.sort_values('float_shares')

# Save to new CSV
output_file = 'ultra_low_float_stocks.csv'
ultra_low_float.to_csv(output_file, index=False)

print(f"\n✓ Saved to {output_file}")
print(f"\nFloat range:")
print(f"  Lowest: {ultra_low_float['float_shares'].min():,.0f} shares")
print(f"  Highest: {ultra_low_float['float_shares'].max():,.0f} shares")
print(f"  Median: {ultra_low_float['float_shares'].median():,.0f} shares")
