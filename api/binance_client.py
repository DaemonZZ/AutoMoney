# api/binance_client.py

from binance.client import Client
from core.runtime_config import runtime_config
import os
_client = None

def get_client():
    global _client

    if _client is not None:
        return _client

    print(f"[binance_client] MODE: market={runtime_config.market}, net={runtime_config.net}")
    API_KEY = os.getenv("BINANCE_API_KEY")
    API_SECRET = os.getenv("BINANCE_API_SECRET")
    client = Client(
        api_key=API_KEY,
        api_secret=API_SECRET
    )

    # Spot Testnet
    if runtime_config.is_spot and runtime_config.is_testnet:
        client.API_URL = "https://testnet.binance.vision/api"
        print("[binance_client] SPOT TESTNET")

    # Futures Testnet
    if runtime_config.is_futures and runtime_config.is_testnet:
        print("[binance_client] FUTURES TESTNET (UM)")
        # python-binance tự switch endpoint dựa trên futures_* call

    # Real Trading
    if runtime_config.net == "real":
        print("[binance_client] REAL TRADING")

    _client = client
    return _client
