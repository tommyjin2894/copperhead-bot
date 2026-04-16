"""V5: Hybrid - 상황에 따라 전략을 전환하는 적응형 봇.
  - 짧을 때: 공격적 음식 수집
  - 길 때: 상대 가두기 + stalemate 유도
  - 같을 때: 포도 우선 + 차단
"""
from strategies.base import BaseBot
from collections import deque


class Bot(BaseBot):
    def __init__(self, server_url, name="V5-Hybrid"):
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

        # === DETERMINE PHASE ===
        length_diff = s["length"] - s["opp_length"]
        if length_diff >= 3:
            phase = "dominate"   # 압도적 우위: 가두기 + stalemate
        elif length_diff >= 1:
            phase = "pressure"   # 약간 우위: 공격적 차단
        elif length_diff <= -2:
            phase = "desperate"  # 열세: 극공격 음식 수집
        else:
            phase = "balanced"   # 비슷: 포도 우선 + 안전

        scores = {}
        for m in cands:
            sc = 0.0
            mx, my = m["x"], m["y"]

            # --- Always: escape routes ---
            esc = sum(1 for dx, dy in DIRS.values()
                      if 0 <= mx+dx < s["W"] and 0 <= my+dy < s["H"]
                      and (mx+dx, my+dy) not in occ)
            esc_weight = 120 if phase == "dominate" else 80
            sc += esc * esc_weight

            # --- Always: wall ---
            edge = min(mx, s["W"]-1-mx, my, s["H"]-1-my)
            if edge == 0:
                sc -= 150
            elif edge == 1:
                sc -= 50
            else:
                sc += edge * 10

            # --- Always: space ---
            sc += min(m.get("reach", 0), 80) * (8 if phase == "dominate" else 5)

            # --- Head collision ---
            if (mx, my) in opp_next:
                if length_diff >= 2:
                    sc += 5000
                elif length_diff == 1:
                    sc += 2000 if opp_pred and (mx, my) == opp_pred else 500
                elif length_diff == 0:
                    sc -= 8000  # equal = too risky
                else:
                    sc -= 12000

            # --- Phase-specific food logic ---
            best_fv = 0
            for f in s["foods"]:
                fx, fy = f["x"], f["y"]
                ft = f.get("type", "apple")
                lt = f.get("lifetime")
                nd = self.manhattan((mx, my), (fx, fy))
                od = self.manhattan(s["opp_head"], (fx, fy)) if s["opp_head"] else 999

                if ft == "grapes" and lt is not None and lt < nd + 2:
                    continue

                fv = 0

                if phase == "dominate":
                    # Only eat if convenient, focus on trapping
                    if mx == fx and my == fy:
                        fv = 1500 if ft == "grapes" else 600
                    elif nd <= 3 and nd < od:
                        fv = 800 if ft == "grapes" else 300
                    # AVOID food if it takes us away from trapping
                    if nd > 5:
                        fv = 0

                elif phase == "pressure":
                    if mx == fx and my == fy:
                        fv = 2500 if ft == "grapes" else 1200
                    elif nd < od:
                        base = 3500 if ft == "grapes" else 1200
                        fv = base - nd * 45

                elif phase == "desperate":
                    # EAT EVERYTHING, don't care about distance advantage
                    if mx == fx and my == fy:
                        fv = 4000 if ft == "grapes" else 2000
                    else:
                        base = 5000 if ft == "grapes" else 2000
                        fv = base - nd * 40

                else:  # balanced
                    if mx == fx and my == fy:
                        fv = 3000 if ft == "grapes" else 1300
                    elif nd <= od:
                        base = 3500 if ft == "grapes" else 1200
                        fv = base - nd * 45
                    elif ft == "grapes" and nd <= 6:
                        fv = 2000 - nd * 60

                best_fv = max(best_fv, fv)
            sc += best_fv

            # --- Trapping (dominate/pressure phases) ---
            if phase in ("dominate", "pressure") and s["opp_head"]:
                if m.get("reach", 0) > need:
                    ob = set(flood_b)
                    ob.add((mx, my))
                    opp_sp = self.flood_fill(
                        s["opp_head"][0], s["opp_head"][1],
                        ob, s["W"], s["H"], 60)
                    trap_mult = 40 if phase == "dominate" else 25
                    space_adv = m.get("reach", 0) - opp_sp
                    sc += space_adv * trap_mult
                    if opp_sp < s["opp_length"] + 3:
                        sc += 6000
                    elif opp_sp < s["opp_length"] + 8:
                        sc += 2500

            # --- Tail chase (when no food target) ---
            if best_fv < 300:
                td = self.manhattan((mx, my), s["tail"])
                sc += max(0, 8 - td) * 20

            # --- Stalemate ---
            if not s["foods"] and s["length"] > s["opp_length"]:
                cx, cy = s["W"] // 2, s["H"] // 2
                sc -= self.manhattan((mx, my), (cx, cy)) * 25
                sc += esc * 150

            scores[m["dir"]] = sc

        return max(scores, key=scores.get)
