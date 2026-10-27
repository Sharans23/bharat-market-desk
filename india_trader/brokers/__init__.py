"""Broker registry: adding an adapter does not implicitly enable trade execution."""
from .adapters import Kite, Dhan, Groww
from .credentials import Vault
from .transport import BrokerError

ADAPTERS = {"kite": Kite, "dhan": Dhan, "groww": Groww}


def connect(broker, credentials=None, transport=None):
    if broker not in ADAPTERS:
        raise BrokerError("Supported brokers: kite, dhan, groww")
    return ADAPTERS[broker](credentials if credentials is not None else Vault().load(broker), transport)
