"""V4: Cut-off - 상대와 음식 사이에 위치해서 굶기는 전략."""
from strategies.base import BaseBot
from collections import deque


class Bot(BaseBot):
    def __init__(self, server_url, name="V4-Cutoff"):
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
            sc += edge * 10 if edge > 1 else (-130 if edge == 0 else -40)

            if (mx, my) in opp_next:
                diff = s["length"] - s["opp_length"]
                if diff >= 2:
                    sc += 4000
                elif diff == 1:
                    sc += 1200
                else:
                    sc -= 10000

            # === KEY STRATEGY: CUT-OFF & INTERCEPTION ===
            # For EACH food, check if we can get between opponent and food
            best_food = 0
            for f in s["foods"]:
                fx, fy = f["x"], f["y"]
                ft = f.get("type", "apple")
                my_d = self.manhattan((mx, my), (fx, fy))
                opp_d = self.manhattan(s["opp_head"], (fx, fy)) if s["opp_head"] else 999

                fv = 0
                if mx == fx and my == fy:
                    fv += 2500 if ft == "grapes" else 1200
                elif my_d < opp_d:
                    # We're closer: eat it
                    base = 3500 if ft == "grapes" else 1200
                    fv = base - my_d * 45
                elif my_d == opp_d and s["length"] > s["opp_length"]:
                    # Equal distance but we're longer: race for it
                    base = 2500 if ft == "grapes" else 800
                    fv = base - my_d * 50
                elif opp_d <= 6:
                    # Opponent is close to food: try to block their path
                    # Position ourselves between opponent and food
                    # Check if we're on the line between opp and food
                    if s["opp_head"]:
                        oh = s["opp_head"]
                        # Midpoint between opponent and food
                        mid_x = (oh[0] + fx) // 2
                        mid_y = (oh[1] + fy) // 2
                        mid_dist = self.manhattan((mx, my), (mid_x, mid_y))
                        if mid_dist <= 2:
                            fv += 600  # good blocking position

                best_food = max(best_food, fv)
            sc += best_food

            # Stalemate: if we're longer, play center + safe
            if not s["foods"]:
                if s["length"] > s["opp_length"]:
                    cx, cy = s["W"] // 2, s["H"] // 2
                    sc -= self.manhattan((mx, my), (cx, cy)) * 20
                    sc += esc * 150

            sc += min(m.get("reach", 0), 60) * 5

            # Tail chase safety
            td = self.manhattan((mx, my), s["tail"])
            if best_food < 300:
                sc += max(0, 8 - td) * 20

            scores[m["dir"]] = sc

        return max(scores, key=scores.get)
