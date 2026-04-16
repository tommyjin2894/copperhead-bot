"""V2: Defensive - 생존 최우선, 공간 확보, 상대 유인."""
from strategies.base import BaseBot
from collections import deque


class Bot(BaseBot):
    def __init__(self, server_url, name="V2-Defensive"):
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

        flood_b = set(occ)
        flood_b.add(s["head"])
        flood_b.discard(s["tail"])
        roomy = []
        need = max(s["length"] + 4, 12)  # MORE buffer
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

            # HEAVY escape weight
            esc = sum(1 for dx, dy in DIRS.values()
                      if 0 <= mx+dx < s["W"] and 0 <= my+dy < s["H"]
                      and (mx+dx, my+dy) not in occ)
            sc += esc * 120

            # HEAVY space weight
            sc += min(m.get("reach", 0), 100) * 8

            # Wall: VERY careful
            edge = min(mx, s["W"]-1-mx, my, s["H"]-1-my)
            sc += edge * 15 if edge > 1 else (-200 if edge == 0 else -80)

            # ALWAYS avoid opponent head area
            if (mx, my) in opp_next:
                sc -= 12000

            # Food: only if safe and close
            for f in s["foods"]:
                fx, fy = f["x"], f["y"]
                ft = f.get("type", "apple")
                nd = self.manhattan((mx, my), (fx, fy))
                od = self.manhattan(s["opp_head"], (fx, fy)) if s["opp_head"] else 999
                if nd < od:  # only if we're closer
                    if mx == fx and my == fy:
                        sc += 2000 if ft == "grapes" else 1000
                    elif nd <= 5:
                        base = 2500 if ft == "grapes" else 800
                        sc += base - nd * 50

            # Tail chasing for safety
            td = self.manhattan((mx, my), s["tail"])
            sc += max(0, 8 - td) * 25

            # Opponent space pressure
            if s["opp_head"] and m.get("reach", 0) > need:
                ob = set(flood_b)
                ob.add((mx, my))
                os = self.flood_fill(s["opp_head"][0], s["opp_head"][1],
                                     ob, s["W"], s["H"], 30)
                if os < s["opp_length"] + 3:
                    sc += 2000

            scores[m["dir"]] = sc

        return max(scores, key=scores.get)
