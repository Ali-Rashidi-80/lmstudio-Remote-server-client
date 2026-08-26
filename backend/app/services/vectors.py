"""Vector helpers."""

from __future__ import annotations

import math


def l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if not norm:
        return vec
    return [x / norm for x in vec]
