"""Bounded, prospective capture. No rolling history outside a requested window."""
import time

RATE = 16000
SECONDS = 10
MAX_BYTES = RATE * SECONDS * 2


class Window:
    def __init__(self, reason, now=None):
        self.reason = reason
        self.started = time.monotonic() if now is None else now
        self.data = bytearray()

    def add(self, pcm, now=None):
        if len(pcm) % 2:
            raise ValueError("PCM16 must contain whole samples")
        now = time.monotonic() if now is None else now
        if now - self.started >= SECONDS:
            return False
        remaining = MAX_BYTES - len(self.data)
        self.data.extend(pcm[:remaining])
        return remaining > len(pcm)

    def take(self):
        result = bytes(self.data)
        self.data.clear()
        return result
