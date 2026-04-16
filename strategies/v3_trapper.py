"""V3: Trapper - 상대를 벽/코너에 가둬서 죽이는 전략."""
from strategies.base import BaseBot
from collections import deque


class Bot(BaseBot):
    def __init__(self, server_url, name="V3-Trapper"):
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

            esc = sum(1 for dx, dy in DIRS.values()
                      if 0 <= mx+dx < s["W"] and 0 <= my+dy < s["H"]
                      and (mx+dx, my+dy) not in occ)
            sc += esc * 80

            edge = min(mx, s["W"]-1-mx, my, s["H"]-1-my)
            sc += edge * 10 if edge > 1 else (-150 if edge == 0 else -50)

            # Head collision
            if (mx, my) in opp_next:
                diff = s["length"] - s["opp_length"]
                if diff >= 2:
                    sc += 4000
                elif diff == 1:
                    sc += 1000 if opp_pred and (mx, my) == opp_pred else -500
                else:
                    sc -= 10000

            # Food
            for f in s["foods"]:
                fx, fy = f["x"], f["y"]
                ft = f.get("type", "apple")
                nd = self.manhattan((mx, my), (fx, fy))
                od = self.manhattan(s["opp_head"], (fx, fy)) if s["opp_head"] else 999
                if nd <= od:
                    if mx == fx and my == fy:
                        sc += 2500 if ft == "grapes" else 1200
                    else:
                        base = 3000 if ft == "grapes" else 1000
                        sc += base - nd * 45

            # === KEY STRATEGY: TRAP THE OPPONENT ===
            # Minimize opponent's reachable space
            if s["opp_head"] and m.get("reach", 0) > need:
                ob = set(flood_b)
                ob.add((mx, my))
                opp_space = self.flood_fill(
                    s["opp_head"][0], s["opp_head"][1],
                    ob, s["W"], s["H"], 80)
                my_space = m.get("reach", 0)

                # The bigger the space difference, the better
                space_advantage = my_space - opp_space
                sc += space_advantage * 30

                # HUGE bonus if trapping opponent
                if opp_space < s["opp_length"] + 3:
                    sc += 5000
                elif opp_space < s["opp_length"] + 8:
                    sc += 2000
                elif opp_space < 20:
                    sc += 800

            # Move toward opponent to pressure them
            if s["opp_head"]:
                cur_d = self.manhattan(s["head"], s["opp_head"])
                new_d = self.manhattan((mx, my), s["opp_head"])
                if new_d < cur_d and s["length"] >= s["opp_length"]:
                    sc += 300

            sc += min(m.get("reach", 0), 60) * 5
            scores[m["dir"]] = sc

        return max(scores, key=scores.get)
