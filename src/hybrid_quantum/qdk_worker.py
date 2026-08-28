from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Sequence
from typing import Any


def _shot_index(shot: Sequence[Any]) -> int:
    index = 0
    for qubit, result in enumerate(shot):
        if str(result).lower().endswith("one") or str(result) == "1":
            index |= 1 << qubit
    return index


def main() -> None:
    from qdk import qsharp

    payload = json.load(sys.stdin)
    operation = str(payload["operation"])
    source = str(payload["source"])
    shots = int(payload["shots"])
    qsharp.eval(source)
    measured = qsharp.run(f"{operation}()", shots=shots)
    counts = Counter(_shot_index(shot) for shot in measured)
    json.dump({"counts": {str(index): count for index, count in counts.items()}}, sys.stdout)


if __name__ == "__main__":
    main()
