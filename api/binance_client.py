# api/binance_client.py

from binance.client import Client
from core.runtime_config import runtime_config
import os

# ===============================================================
# FIX: KHỞI TẠO BIẾN TRƯỚC KHI SỬ DỤNG
# ===============================================================
_client = None
_client_futures = None
# ===============================================================


def get_client():
    global _client

    if _client is not None:
        return _client

    print(f"[binance_client] MODE: market={runtime_config.market}, net={runtime_config.net}")

    API_KEY = os.getenv("BINANCE_API_KEY")
    API_SECRET = os.getenv("BINANCE_API_SECRET")

    client = Client(
        api_key=API_KEY,
        api_secret=API_SECRET,
    )

    # Spot Testnet
    if runtime_config.is_spot and runtime_config.is_testnet:
        client.API_URL = "https://testnet.binance.vision/api"
        print("[binance_client] SPOT TESTNET")

    # Futures Testnet
    if runtime_config.is_futures and runtime_config.is_testnet:
        print("[binance_client] FUTURES TESTNET (UM)")

    # Real Trading
    if runtime_config.net == "real":
        print("[binance_client] REAL TRADING")

    _client = client
    return _client


def get_futures_client():
    """
    Trả về client futures dùng cho mọi module.
    Không tạo client mới – chỉ dùng client chung.
    """
    global _client_futures

    if _client_futures is not None:
        return _client_futures

    # Dùng chung 1 client cho spot/futures
    c = get_client()
    _client_futures = c
    return _client_futures


# Giúp import trực tiếp: from api.binance_client import client_futures
client_futures = get_futures_client()
