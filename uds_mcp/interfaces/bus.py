"""Open a python-can bus for one of the supported interface names."""

from __future__ import annotations

import can

# Our CLI names -> python-can interface names.
PYTHON_CAN_INTERFACES = {
    "sim": "virtual",
    "pcan": "pcan",
    "intrepid": "neovi",
    "vector": "vector",
    "socketcan": "socketcan",
}

DEFAULT_CHANNELS = {
    "sim": "uds-mcp",
    "pcan": "PCAN_USBBUS1",
    "intrepid": 1,
    "vector": 0,
    "socketcan": "can0",
}


def open_bus(
    interface: str,
    channel: str | int | None = None,
    bitrate: int = 500_000,
    fd: bool = False,
    data_bitrate: int | None = None,
) -> can.BusABC:
    try:
        backend = PYTHON_CAN_INTERFACES[interface]
    except KeyError:
        raise ValueError(f"Unknown interface {interface!r}") from None

    kwargs: dict = {
        "interface": backend,
        "channel": DEFAULT_CHANNELS[interface] if channel is None else channel,
    }
    if interface != "sim":
        kwargs["bitrate"] = bitrate
        if fd:
            kwargs["fd"] = True
            if data_bitrate:
                kwargs["data_bitrate"] = data_bitrate
    return can.Bus(**kwargs)
