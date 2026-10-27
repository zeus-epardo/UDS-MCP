"""Serve a :class:`SimulatedEcu` over ISO-TP on any python-can bus.

On a PC this is the ``virtual`` bus; on a Raspberry Pi with a CAN HAT it is SocketCAN.
"""

from __future__ import annotations

import threading
import time

import can
import isotp

from uds_mcp.core.config import EcuConfig
from uds_mcp.sim.ecu import SimulatedEcu


class SimulatorServer:
    """Answers UDS requests on ``bus`` in a background thread. The bus is owned by the caller."""

    def __init__(self, bus: can.BusABC, config: EcuConfig) -> None:
        self.ecu = SimulatedEcu(config)
        ecu = config.ecu
        mode = (
            isotp.AddressingMode.Normal_29bits
            if max(ecu.request_id, ecu.response_id) > 0x7FF
            else isotp.AddressingMode.Normal_11bits
        )
        # The simulator listens on the request ID and answers on the response ID.
        address = isotp.Address(mode, txid=ecu.response_id, rxid=ecu.request_id)
        params = {
            "tx_padding": 0xCC,
            "can_fd": ecu.can_fd,
            "tx_data_length": 64 if ecu.can_fd else 8,
            "bitrate_switch": ecu.can_fd,
        }
        self._notifier = can.Notifier(bus, [])
        self._stack = isotp.NotifierBasedCanStack(
            bus, self._notifier, address=address, params=params
        )
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="uds-sim", daemon=True)

    def start(self) -> SimulatorServer:
        self._stack.start()
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._stack.stop()
        self._notifier.stop()

    def __enter__(self) -> SimulatorServer:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _serve(self) -> None:
        while not self._stop.is_set():
            request = self._stack.recv(block=True, timeout=0.05)
            if request is None:
                self.ecu.check_s3()
                continue
            for delay, response in self.ecu.handle(bytes(request)):
                if delay and self._stop.wait(delay):
                    return
                self._stack.send(response)
                # Wait for multi-frame responses to leave before sending the next one.
                while self._stack.transmitting() and not self._stop.is_set():
                    time.sleep(0.001)
