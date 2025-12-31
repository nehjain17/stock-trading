#!/usr/bin/env python3
from ib_insync import IB, ScannerSubscription, Stock
import os
from dotenv import load_dotenv

load_dotenv()

ib = IB()
port = int(os.getenv('IBKR_PORT', '7497'))

print(f"Connecting to IBKR on 127.0.0.1:{port}...")

errors = []

def onError(reqId, errorCode, errorString, advancedOrderRejectJson=''):
    msg = f"IB Error {errorCode}, reqId {reqId}: {errorString}"
    print(msg)
    errors.append(msg)

ib.errorEvent += onError

ib.connect('127.0.0.1', port, clientId=123, readonly=True, timeout=15)
print(f"Connected: {ib.isConnected()}")
print(f"Server version: {ib.client.serverVersion}")

try:
    ib.reqMarketDataType(1)
    print("Market data type: real-time (1)")
except Exception as e:
    print(f"Failed to set market data type: {e}")

# Test simple market data
print("\nTesting simple market data on AAPL...")
contract = Stock('AAPL', 'SMART', 'USD')
tkr = ib.reqMktData(contract, '', False, False)
ib.sleep(1.0)
print(f"AAPL last: {tkr.last}, bid: {tkr.bid}, ask: {tkr.ask}, volume: {tkr.volume}")
ib.cancelMktData(contract)

# Test scanner
print("\nTesting scanner TOP_PERC_GAIN at STK.US...")
sub = ScannerSubscription(instrument='STK', locationCode='STK.US', scanCode='TOP_PERC_GAIN', numberOfRows=50)
results = ib.reqScannerData(sub)
ib.sleep(2.0)
print(f"Scanner results: {len(results)}")
if results:
    for i, item in enumerate(results[:10], 1):
        print(f"  {i}. {item.contractDetails.contract.symbol}")

print("\nTesting scanner TOP_PERC_GAIN at STK.US.MAJOR...")
sub2 = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR', scanCode='TOP_PERC_GAIN', numberOfRows=50)
results2 = ib.reqScannerData(sub2)
ib.sleep(2.0)
print(f"Scanner results (MAJOR): {len(results2)}")

print("\nCollected errors:")
for e in errors:
    print("  -", e)

ib.disconnect()
print("Disconnected.")
