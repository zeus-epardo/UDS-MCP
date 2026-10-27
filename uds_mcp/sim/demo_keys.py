"""Demo security-access key algorithm for the simulator.

Deliberately trivial and public. Real key algorithms are secret and must never be added
to this repository; point ``[security]`` at your own private module instead.
"""


def xor_ff(level: int, seed: bytes) -> bytes:
    return bytes(b ^ 0xFF for b in seed)
