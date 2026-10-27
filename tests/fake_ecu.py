"""Minimal scripted ECU on a python-can virtual bus, used by the core tests.

It answers a fixed set of requests and is intentionally dumb; the configurable
simulator lives in ``uds_mcp.sim``.
"""

from __future__ import annotations

import threading

import can
import isotp

SEED = bytes.fromhex("11223344")
DIDS = {
    0xF190: b"WDB00000000000001",  # VIN, 17 ASCII bytes
    0xF186: b"\x01",  # active session
    0x0100: b"\xde\xad\xbe\xef",  # not in the test config: read as raw bytes
}
WRITABLE = {0xF190}
DTCS = [(0x123456, 0x2F), (0xC07300, 0x08)]


def key_for(seed: bytes) -> bytes:
    return bytes(b ^ 0xFF for b in seed)


def nrc(sid: int, code: int) -> bytes:
    return bytes([0x7F, sid, code])


class FakeEcu:
    def __init__(self, channel: str, request_id: int = 0x7E0, response_id: int = 0x7E8) -> None:
        self.bus = can.Bus(interface="virtual", channel=channel)
        self.notifier = can.Notifier(self.bus, [])
        address = isotp.Address(
            isotp.AddressingMode.Normal_11bits, txid=response_id, rxid=request_id
        )
        self.stack = isotp.NotifierBasedCanStack(self.bus, self.notifier, address=address)
        self.unlocked = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> FakeEcu:
        self.stack.start()
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.stack.stop()
        self.notifier.stop()
        self.bus.shutdown()

    def _serve(self) -> None:
        while not self._stop.is_set():
            request = self.stack.recv(block=True, timeout=0.05)
            if request:
                response = self.respond(bytes(request))
                if response:
                    self.stack.send(response)

    def respond(self, req: bytes) -> bytes | None:
        sid = req[0]
        if sid == 0x10:
            # P2 = 1000 ms, P2* = 500 * 10 ms
            return bytes([0x50, req[1], 0x03, 0xE8, 0x01, 0xF4])
        if sid == 0x11:
            return bytes([0x51, req[1]])
        if sid == 0x22:
            out = bytearray([0x62])
            for i in range(1, len(req), 2):
                did = int.from_bytes(req[i : i + 2], "big")
                if did not in DIDS:
                    return nrc(sid, 0x31)
                out += req[i : i + 2] + DIDS[did]
            return bytes(out)
        if sid == 0x2E:
            did = int.from_bytes(req[1:3], "big")
            if did not in WRITABLE:
                return nrc(sid, 0x31)
            DIDS[did] = req[3:]
            return bytes([0x6E]) + req[1:3]
        if sid == 0x27:
            level = req[1]
            if level % 2:
                seed = bytes(len(SEED)) if self.unlocked else SEED
                return bytes([0x67, level]) + seed
            if req[2:] != key_for(SEED):
                return nrc(sid, 0x35)
            self.unlocked = True
            return bytes([0x67, level])
        if sid == 0x31:
            return bytes([0x71, req[1]]) + req[2:4] + b"\x00"
        if sid == 0x19 and req[1] == 0x02:
            out = bytearray([0x59, 0x02, 0xFF])
            for dtc, status in DTCS:
                if status & req[2]:
                    out += dtc.to_bytes(3, "big") + bytes([status])
            return bytes(out)
        if sid == 0x14:
            return bytes([0x54])
        if sid == 0x3E:
            return None if req[1] & 0x80 else bytes([0x7E, 0x00])
        return nrc(sid, 0x11)
