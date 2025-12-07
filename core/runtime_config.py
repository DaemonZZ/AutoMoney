from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    market: str = "futures"   # "spot" hoặc "futures"
    net: str = "test"      # "real" hoặc "test"

    @property
    def is_spot(self):
        return self.market.lower() == "spot"

    @property
    def is_futures(self):
        return self.market.lower() == "futures"

    @property
    def is_testnet(self):
        return self.net.lower() == "test"

    @property
    def is_real(self):
        return self.net.lower() == "real"


runtime_config = RuntimeConfig()

