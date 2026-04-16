"""V1: Aggressive - 빠르게 먹고 정면충돌 적극 유도."""
from strategies.base import BaseBot
from collections import deque


class Bot(BaseBot):
    def __init__(self, server_url, name="V1-Aggressive"):
        super().__init__(server_url, name)

    def calculate_move(self):
        s = self.get_state()
        if not s:
            return None

        DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        occ = self.build_occupied(s)
        safe = self.get_safe_moves(s["head"], s["dir"], occ, s["W"], s["H"])
        if not safe:
            OPP = {"up": "down", "down": "up", "left": "right", "right": "left"}
            for d in DIRS:
                if d != OPP.get(s["dir"]):
                    return d
            return s["dir"]

        opp_next, opp_pred = self.get_opp_real_next(s)

        # Flood fill filter
        flood_b = set(occ)
        flood_b.add(s["head"])
        flood_b.discard(s["tail"])
        roomy = []
        need = max(s["length"] + 2, 8)
        for m in safe:
            r = self.flood_fill(m["x"], m["y"], flood_b, s["W"], s["H"], need + 1)
            m["reach"] = r
            if r >= need:
                roomy.append(m)
        cands = roomy if roomy else safe

        scores = {}
        for m in cands:
            sc = 0.0
            mx, my = m["x"], m["y"]

            # Escape
            esc = sum(1 for dx, dy in DIRS.values()
                      if 0 <= mx+dx < s["W"] and 0 <= my+dy < s["H"]
                      and (mx+dx, my+dy) not in occ)
            sc += esc * 70

            # Wall
            edge = min(mx, s["W"]-1-mx, my, s["H"]-1-my)
            sc += edge * 8 if edge > 1 else (-120 if edge == 0 else -40)

            # AGGRESSIVE head-on: seek collision when >= length
            if (mx, my) in opp_next:
                diff = s["length"] - s["opp_length"]
                if diff >= 1:
                    sc += 5000 if opp_pred and (mx, my) == opp_pred else 2000
                else:
                    sc -= 10000

            # Food: chase EVERYTHING aggressively
            for f in s["foods"]:
                fx, fy = f["x"], f["y"]
                ft = f.get("type", "apple")
                nd = self.manhattan((mx, my), (fx, fy))
                if mx == fx and my == fy:
                    sc += 3000 if ft == "grapes" else 1500
                else:
                    base = 4000 if ft == "grapes" else 1500
                    sc += base - nd * 60

            sc += min(m.get("reach", 0), 60) * 4
            scores[m["dir"]] = sc

        return max(scores, key=scores.get)
