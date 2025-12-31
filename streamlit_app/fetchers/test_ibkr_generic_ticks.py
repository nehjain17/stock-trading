#!/usr/bin/env python3
"""
Quick IBKR generic tick diagnostic for selected symbols.
Checks volume and generic ticks 236 (shortable), 294 (trades/min), 295 (volume/min).
"""
import argparse
import time
from ib_insync import IB, Stock


def test_symbol(ib: IB, symbol: str, wait_sec: float = 1.5):
    c = Stock(symbol, 'SMART', 'USD')
    base = ib.reqMktData(c, '', False, False)
    gen = ib.reqMktData(c, '236,294,295', False, False)
    waited = 0.0
    while waited < wait_sec:
        has_any = any([
            base.volume is not None,
            hasattr(gen, 'shortableShares') and gen.shortableShares is not None,
            hasattr(gen, 'tradeRate') and gen.tradeRate is not None,
            hasattr(gen, 'volumeRate') and gen.volumeRate is not None,
        ])
        if has_any:
            break
        ib.sleep(0.2)
        waited += 0.2
    try:
        ib.cancelMktData(c)
    except Exception:
        pass
    return {
        'symbol': symbol,
        'volume': getattr(base, 'volume', None),
        'shortableShares': getattr(gen, 'shortableShares', None),
        'tradeRate': getattr(gen, 'tradeRate', None),
        'volumeRate': getattr(gen, 'volumeRate', None),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=7496)
    p.add_argument('--symbols', type=str, default='FLYE,AEHL,AAPL')
    p.add_argument('--wait-sec', type=float, default=1.5)
    args = p.parse_args()

    ib = IB()
    ib.connect('127.0.0.1', args.port, clientId=777, readonly=True, timeout=20)
    print(f"✓ Connected to IBKR on port {args.port}")
    # Force delayed data mode to test if any data is delivered
    try:
        ib.reqMarketDataType(3)
        print("✓ Forced market data type: delayed")
    except Exception as e:
        print(f"⚠ Could not set delayed data mode: {e}")

    syms = [s.strip() for s in args.symbols.split(',') if s.strip()]
    print(f"Testing symbols: {', '.join(syms)}")
    for s in syms:
        res = test_symbol(ib, s, wait_sec=args.wait_sec)
        print(f"{res['symbol']}: volume={res['volume']} shortable={res['shortableShares']} tradeRate={res['tradeRate']} volumeRate={res['volumeRate']}")

    ib.disconnect()


if __name__ == '__main__':
    main()
