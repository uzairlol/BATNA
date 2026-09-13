"""Stress: concurrent sessions on the live API over real Redis; WS is gapless.

Starts four negotiations concurrently on one event loop, then opens a WS per
session (which for an already-steaming session replays the buffer then streams
live) and asserts a gapless session_start..session_end with monotonic seq.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from fastapi.testclient import TestClient

from batna.api.main import app


def main() -> None:
    kinds = ["wide", "narrow", "asymmetric", "no_zopa"]
    with TestClient(app) as client:
        sids = []
        for k in kinds:
            r = client.post(f"/api/sessions?kind={k}")
            assert r.status_code == 201
            sids.append(r.json()["session_id"])
        # Fire all four negotiations concurrently (background tasks).
        for sid in sids:
            r = client.post(f"/api/sessions/{sid}/negotiate")
            assert r.status_code == 200, r.text

        all_ok = True
        for sid, k in zip(sids, kinds, strict=True):
            seqs: list[int] = []
            types: list[str] = []
            start = time.time()
            with client.websocket_connect(f"/api/ws/{sid}") as ws:
                while time.time() - start < 30:
                    data = ws.receive_json()
                    seqs.append(data["seq"])
                    types.append(data["type"])
                    if data["type"] == "session_end":
                        break
            mono = seqs == list(range(len(seqs)))
            first = types[0] if types else "NONE"
            last = types[-1] if types else "NONE"
            offers = types.count("offer")
            ok = first == "session_start" and last == "session_end" and mono
            all_ok &= ok
            print(
                f"[{k}] {sid[:6]} -> n={len(types)} first={first} last={last} "
                f"offers={offers} mono={mono} {'OK' if ok else 'FAIL'}"
            )
            g = client.get(f"/api/sessions/{sid}").json()
            print(f"         status={g['status']} mode={g['run_mode']}/{g['run_model']}")

        print("STRESS_OK" if all_ok else "STRESS_FAILED")
        raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
