"""One-off: correct pc_story video clip costs to the billed wan-3-0 480p rate
($0.02/s, $0.16 per 8s clip). Updates sidecars + state.json; appends a
correction note to the run log instead of rewriting history."""

import json
from pathlib import Path

RATE = 0.02
DUR = 8
ROOT = Path("projects/pc_story")

# sidecars
for shot in ("S01", "S02", "S03", "S04"):
    meta_path = ROOT / f"assets/shots/{shot}/motion/candidates/clip_v01.mp4.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    old = meta.get("cost_usd")
    meta["cost_usd"] = round(RATE * DUR, 4)
    meta["cost_note"] = (f"corrected to billed rate {RATE}/s (was {old}); "
                         "wan-3-0 480p actual charge $0.16/clip")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"{shot}: sidecar cost_usd {old} -> {meta['cost_usd']}")

# state.json
state_path = ROOT / "state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
for key, st in state.get("assets", {}).items():
    if not key.startswith("video_"):
        continue
    u = st.get("usage")
    if not u:
        continue
    old = u.get("cost_usd")
    u["cost_usd"] = round(RATE * DUR, 4)
    print(f"{key}: state cost_usd {old} -> {u['cost_usd']}")
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

# correction note in the newest run log
logs = sorted((ROOT / "logs").glob("run_*.log"))
with open(logs[-1], "a", encoding="utf-8") as f:
    f.write(f"correction  video clips S01-S04 re-rated to wan-3-0 480p "
            f"billed ${RATE}/s: ${round(RATE*DUR,2)} per clip "
            f"(earlier estimates on these lines were list-price guesses)\n")
print("correction line appended to", logs[-1].name)
