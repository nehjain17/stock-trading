#!/usr/bin/env python3
"""
Fetch shortable shares data from IBKR's FTP server.
This is a bulk alternative to the API for daily data.
"""
import ftplib
import pandas as pd
import io
from datetime import datetime

# IBKR FTP settings
FTP_HOST = 'ftp3.interactivebrokers.com'
FTP_USER = 'shortstock'
FTP_PASS = ''  # Anonymous login

def fetch_shortable_from_ftp():
    """Download shortable stocks file from IBKR FTP"""
    try:
        print("Connecting to IBKR FTP server...")
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        
        print("✓ Connected to IBKR FTP")
        
        # List available files
        files = []
        ftp.retrlines('LIST', files.append)
        print(f"\nAvailable files:")
        for f in files:
            print(f"  {f}")
        
        # Try to find the latest shortable stocks file
        # Usually named something like "usa.txt" or dated files
        file_list = ftp.nlst()
        print(f"\nFile list: {file_list}")
        
        # Look for USA stocks file
        target_file = None
        for fname in file_list:
            if 'usa' in fname.lower() or 'us' in fname.lower():
                target_file = fname
                break
        
        if not target_file and file_list:
            target_file = file_list[0]  # Use first file if no USA-specific found
        
        if not target_file:
            print("✗ No files found on FTP server")
            ftp.quit()
            return None
        
        print(f"\nDownloading: {target_file}")
        
        # Download file to memory
        data = io.BytesIO()
        ftp.retrbinary(f'RETR {target_file}', data.write)
        data.seek(0)
        
        # Try to parse as CSV/TXT
        try:
            df = pd.read_csv(data, sep='|', header=0)
            print(f"✓ Downloaded {len(df)} rows")
            print(f"\nColumns: {df.columns.tolist()}")
            print(f"\nFirst 5 rows:")
            print(df.head())
            
            ftp.quit()
            return df
        
        except Exception as e:
            print(f"Error parsing file: {e}")
            data.seek(0)
            print("\nRaw content (first 1000 chars):")
            print(data.read(1000).decode('utf-8', errors='ignore'))
            ftp.quit()
            return None
    
    except Exception as e:
        print(f"✗ FTP Error: {e}")
        return None

def process_shortable_data(df):
    """Process and match with our symbol list"""
    try:
        # Load our symbols
        our_symbols = pd.read_csv('us_stock_symbols.csv')
        print(f"\nOur symbols: {len(our_symbols)}")
        
        # The IBKR FTP file format varies, but typically has:
        # Symbol, Name, Quantity available, Fee rate, etc.
        # We need to identify the correct columns
        
        if 'SYM' in df.columns:
            symbol_col = 'SYM'
        elif 'Symbol' in df.columns:
            symbol_col = 'Symbol'
        elif 'SYMBOL' in df.columns:
            symbol_col = 'SYMBOL'
        else:
            symbol_col = df.columns[0]  # Assume first column is symbol
        
        # Look for quantity column
        qty_col = None
        for col in df.columns:
            if 'qty' in col.lower() or 'quantity' in col.lower() or 'shares' in col.lower():
                qty_col = col
                break
        
        if not qty_col and len(df.columns) > 2:
            qty_col = df.columns[2]  # Often third column
        
        print(f"Using symbol column: {symbol_col}")
        print(f"Using quantity column: {qty_col}")
        
        # Create clean dataframe
        result = df[[symbol_col, qty_col]].copy()
        result.columns = ['symbol', 'shortable_shares']
        
        # Convert quantity to int
        result['shortable_shares'] = pd.to_numeric(result['shortable_shares'], errors='coerce').fillna(0).astype(int)
        
        # Filter to only our symbols
        result = result[result['symbol'].isin(our_symbols['symbol'])]
        
        print(f"\nMatched {len(result)} symbols from our list")
        print(f"\nSummary statistics:")
        print(result['shortable_shares'].describe())
        
        # Save to CSV
        result.to_csv('shortable_data_ftp.csv', index=False)
        print(f"\n✓ Saved to shortable_data_ftp.csv")
        
        return result
    
    except Exception as e:
        print(f"Error processing data: {e}")
        return None

def main():
    print("IBKR FTP Shortable Shares Downloader")
    print("=" * 50)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    df = fetch_shortable_from_ftp()
    
    if df is not None:
        process_shortable_data(df)

if __name__ == '__main__':
    main()
