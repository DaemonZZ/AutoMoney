# main.py

import argparse
from core.runtime_config import runtime_config
from api.binance_client import get_client

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--market",
        choices=["spot", "futures"],
        help="Chọn thị trường: spot hoặc futures (mặc định lấy từ runtime_config)",
    )
    parser.add_argument(
        "--net",
        choices=["real", "test"],
        help="Chọn network: real hoặc test (mặc định lấy từ runtime_config)",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Chỉ override nếu user truyền
    if args.market is not None:
        runtime_config.market = args.market

    if args.net is not None:
        runtime_config.net = args.net

    print("=== START BOT ===")
    print("Market  :", runtime_config.market)
    print("Network :", runtime_config.net)

    client = get_client()

    if runtime_config.is_spot:
        print("→ Đang dùng SPOT API")
        ks = client.get_klines(symbol="BTCUSDT", interval="5m", limit=2)
    else:
        print("→ Đang dùng FUTURES API")
        ks = client.futures_klines(symbol="BTCUSDT", interval="5m", limit=2)

    print("Sample klines:", ks[:1])


if __name__ == "__main__":
    main()
