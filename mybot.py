#!/usr/bin/env python3
"""
tommy_jhp - CopperHead Snake AI

Usage:
  python3 mybot.py           # 전략 선택 메뉴
  python3 mybot.py 5         # 바로 V5 실행
  python3 mybot.py 3 --name "팀명"
"""

import asyncio
import json
import argparse
import sys
import os
import websockets
from collections import deque

sys.path.insert(0, os.path.dirname(__file__))

SERVER = "wss://copperhead-server.politesmoke-80c82ad7.eastasia.azurecontainerapps.io/ws/"

STRATEGIES = {
    1: ("V1-Aggressive",  "극공격: 빠르게 먹고 정면충돌 유도"),
    2: ("V2-Defensive",   "극방어: 생존 최우선, 꼬리 추적"),
    3: ("V3-Trapper",     "가두기: 상대를 벽/코너에 몰기"),
    4: ("V4-Cutoff",      "차단: 상대-음식 사이 끼어들기"),
    5: ("V5-Hybrid",      "적응형: 상황에 따라 전략 전환 (추천)"),
}


def pick_strategy():
    print("=" * 45)
    print("  tommy_jhp - Strategy Select")
    print("=" * 45)
    for k, (name, desc) in STRATEGIES.items():
        tag = " <<" if k == 5 else ""
        print("  %d) %-16s %s%s" % (k, name, desc, tag))
    print("=" * 45)
    while True:
        try:
            c = int(input("  Select (1-5): "))
            if c in STRATEGIES:
                return c
        except (ValueError, EOFError):
            pass
        print("  1~5 중에 골라주세요!")


# =========================================================================
#  Shared helpers
# =========================================================================

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OPP_DIR = {"up": "down", "down": "up", "left": "right", "right": "left"}


def in_bounds(x, y, W, H):
    return 0 <= x < W and 0 <= y < H


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def flood_fill(sx, sy, blocked, W, H, limit=225):
    if (sx, sy) in blocked:
        return 0
    visited = {(sx, sy)}
    q = deque([(sx, sy)])
    c = 0
    while q:
        x, y = q.popleft()
        c += 1
        if c >= limit:
            return c
        for dx, dy in DIRS.values():
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in visited and (nx, ny) not in blocked:
                visited.add((nx, ny))
                q.append((nx, ny))
    return c


def parse_state(game_state, player_id, W, H):
    snakes = game_state.get("snakes", {})
    me = snakes.get(str(player_id))
    if not me or not me.get("body"):
        return None
    s = {
        "head": (me["body"][0][0], me["body"][0][1]),
        "body": [(p[0], p[1]) for p in me["body"]],
        "length": len(me["body"]),
        "dir": me.get("direction", "right"),
        "tail": (me["body"][-1][0], me["body"][-1][1]),
        "foods": game_state.get("foods", []),
        "W": W, "H": H,
        "opp_head": None, "opp_body": [], "opp_length": 0,
        "opp_dir": None, "opp_tail": None,
    }
    oid = str(3 - player_id)
    opp = snakes.get(oid)
    if opp and opp.get("body") and opp.get("alive", True):
        s["opp_head"] = (opp["body"][0][0], opp["body"][0][1])
        s["opp_body"] = [(p[0], p[1]) for p in opp["body"]]
        s["opp_length"] = len(opp["body"])
        s["opp_dir"] = opp.get("direction")
        s["opp_tail"] = (opp["body"][-1][0], opp["body"][-1][1])
    return s


def build_occ(s):
    occ = set()
    for seg in s["body"][:-1]:
        occ.add(seg)
    for seg in s["opp_body"]:
        occ.add(seg)
    return occ


def get_opp_next(s):
    result = set()
    pred = None
    oh, od = s["opp_head"], s["opp_dir"]
    if oh and od:
        rev = OPP_DIR.get(od)
        for d, (dx, dy) in DIRS.items():
            if d == rev:
                continue
            nx, ny = oh[0] + dx, oh[1] + dy
            if in_bounds(nx, ny, s["W"], s["H"]):
                result.add((nx, ny))
        pdx, pdy = DIRS[od]
        pred = (oh[0] + pdx, oh[1] + pdy)
    return result, pred


def safe_moves(head, cur_dir, occ, W, H):
    moves = []
    for d, (dx, dy) in DIRS.items():
        if d == OPP_DIR.get(cur_dir):
            continue
        nx, ny = head[0] + dx, head[1] + dy
        if in_bounds(nx, ny, W, H) and (nx, ny) not in occ:
            moves.append({"dir": d, "x": nx, "y": ny})
    return moves


def fallback_dir(cur_dir):
    for d in DIRS:
        if d != OPP_DIR.get(cur_dir):
            return d
    return cur_dir


def count_esc(mx, my, occ, W, H):
    return sum(1 for dx, dy in DIRS.values()
               if in_bounds(mx+dx, my+dy, W, H) and (mx+dx, my+dy) not in occ)


def flood_filter(moves, occ, head, tail, W, H, length):
    fb = set(occ)
    fb.add(head)
    fb.discard(tail)
    roomy = []
    need = max(length + 2, 8)
    for m in moves:
        r = flood_fill(m["x"], m["y"], fb, W, H, need + 1)
        m["reach"] = r
        if r >= need:
            roomy.append(m)
    return (roomy if roomy else moves), fb, need


# =========================================================================
#  5 STRATEGIES
# =========================================================================

def calc_v1(s):
    """V1: Aggressive."""
    occ = build_occ(s)
    sm = safe_moves(s["head"], s["dir"], occ, s["W"], s["H"])
    if not sm:
        return fallback_dir(s["dir"])
    opp_n, opp_p = get_opp_next(s)
    cands, fb, need = flood_filter(sm, occ, s["head"], s["tail"], s["W"], s["H"], s["length"])

    scores = {}
    for m in cands:
        sc = 0.0
        mx, my = m["x"], m["y"]
        sc += count_esc(mx, my, occ, s["W"], s["H"]) * 70
        edge = min(mx, s["W"]-1-mx, my, s["H"]-1-my)
        sc += edge * 8 if edge > 1 else (-120 if edge == 0 else -40)
        if (mx, my) in opp_n:
            sc += 5000 if s["length"] > s["opp_length"] else -10000
        for f in s["foods"]:
            fx, fy = f["x"], f["y"]
            nd = manhattan((mx, my), (fx, fy))
            if mx == fx and my == fy:
                sc += 3000 if f.get("type") == "grapes" else 1500
            else:
                sc += (4000 if f.get("type") == "grapes" else 1500) - nd * 60
        sc += min(m.get("reach", 0), 60) * 4
        scores[m["dir"]] = sc
    return max(scores, key=scores.get)


def calc_v2(s):
    """V2: Defensive."""
    occ = build_occ(s)
    sm = safe_moves(s["head"], s["dir"], occ, s["W"], s["H"])
    if not sm:
        return fallback_dir(s["dir"])
    opp_n, _ = get_opp_next(s)
    cands, fb, need = flood_filter(sm, occ, s["head"], s["tail"], s["W"], s["H"], s["length"])

    scores = {}
    for m in cands:
        sc = 0.0
        mx, my = m["x"], m["y"]
        sc += count_esc(mx, my, occ, s["W"], s["H"]) * 120
        sc += min(m.get("reach", 0), 100) * 8
        edge = min(mx, s["W"]-1-mx, my, s["H"]-1-my)
        sc += edge * 15 if edge > 1 else (-200 if edge == 0 else -80)
        if (mx, my) in opp_n:
            sc -= 12000
        for f in s["foods"]:
            fx, fy = f["x"], f["y"]
            nd = manhattan((mx, my), (fx, fy))
            od = manhattan(s["opp_head"], (fx, fy)) if s["opp_head"] else 999
            if nd < od:
                if mx == fx and my == fy:
                    sc += 2000 if f.get("type") == "grapes" else 1000
                elif nd <= 5:
                    sc += (2500 if f.get("type") == "grapes" else 800) - nd * 50
        td = manhattan((mx, my), s["tail"])
        sc += max(0, 8 - td) * 25
        if s["opp_head"] and m.get("reach", 0) > need:
            ob = set(fb); ob.add((mx, my))
            os_ = flood_fill(s["opp_head"][0], s["opp_head"][1], ob, s["W"], s["H"], 30)
            if os_ < s["opp_length"] + 3:
                sc += 2000
        scores[m["dir"]] = sc
    return max(scores, key=scores.get)


def calc_v3(s):
    """V3: Trapper."""
    occ = build_occ(s)
    sm = safe_moves(s["head"], s["dir"], occ, s["W"], s["H"])
    if not sm:
        return fallback_dir(s["dir"])
    opp_n, opp_p = get_opp_next(s)
    cands, fb, need = flood_filter(sm, occ, s["head"], s["tail"], s["W"], s["H"], s["length"])

    scores = {}
    for m in cands:
        sc = 0.0
        mx, my = m["x"], m["y"]
        sc += count_esc(mx, my, occ, s["W"], s["H"]) * 80
        edge = min(mx, s["W"]-1-mx, my, s["H"]-1-my)
        sc += edge * 10 if edge > 1 else (-150 if edge == 0 else -50)
        diff = s["length"] - s["opp_length"]
        if (mx, my) in opp_n:
            if diff >= 2: sc += 4000
            elif diff == 1: sc += (1000 if opp_p and (mx, my) == opp_p else -500)
            else: sc -= 10000
        for f in s["foods"]:
            fx, fy = f["x"], f["y"]
            nd = manhattan((mx, my), (fx, fy))
            od = manhattan(s["opp_head"], (fx, fy)) if s["opp_head"] else 999
            if nd <= od:
                if mx == fx and my == fy:
                    sc += 2500 if f.get("type") == "grapes" else 1200
                else:
                    sc += (3000 if f.get("type") == "grapes" else 1000) - nd * 45
        if s["opp_head"] and m.get("reach", 0) > need:
            ob = set(fb); ob.add((mx, my))
            os_ = flood_fill(s["opp_head"][0], s["opp_head"][1], ob, s["W"], s["H"], 80)
            sa = m.get("reach", 0) - os_
            sc += sa * 30
            if os_ < s["opp_length"] + 3: sc += 5000
            elif os_ < s["opp_length"] + 8: sc += 2000
        if s["opp_head"] and s["length"] >= s["opp_length"]:
            if manhattan((mx, my), s["opp_head"]) < manhattan(s["head"], s["opp_head"]):
                sc += 300
        sc += min(m.get("reach", 0), 60) * 5
        scores[m["dir"]] = sc
    return max(scores, key=scores.get)


def calc_v4(s):
    """V4: Cutoff."""
    occ = build_occ(s)
    sm = safe_moves(s["head"], s["dir"], occ, s["W"], s["H"])
    if not sm:
        return fallback_dir(s["dir"])
    opp_n, opp_p = get_opp_next(s)
    cands, fb, need = flood_filter(sm, occ, s["head"], s["tail"], s["W"], s["H"], s["length"])

    scores = {}
    for m in cands:
        sc = 0.0
        mx, my = m["x"], m["y"]
        sc += count_esc(mx, my, occ, s["W"], s["H"]) * 80
        edge = min(mx, s["W"]-1-mx, my, s["H"]-1-my)
        sc += edge * 10 if edge > 1 else (-130 if edge == 0 else -40)
        diff = s["length"] - s["opp_length"]
        if (mx, my) in opp_n:
            if diff >= 2: sc += 4000
            elif diff == 1: sc += 1200
            else: sc -= 10000
        best_fv = 0
        for f in s["foods"]:
            fx, fy = f["x"], f["y"]
            ft = f.get("type", "apple")
            md = manhattan((mx, my), (fx, fy))
            od = manhattan(s["opp_head"], (fx, fy)) if s["opp_head"] else 999
            fv = 0
            if mx == fx and my == fy:
                fv += 2500 if ft == "grapes" else 1200
            elif md < od:
                fv = (3500 if ft == "grapes" else 1200) - md * 45
            elif md == od and s["length"] > s["opp_length"]:
                fv = (2500 if ft == "grapes" else 800) - md * 50
            elif s["opp_head"] and od <= 6:
                mid = ((s["opp_head"][0]+fx)//2, (s["opp_head"][1]+fy)//2)
                if manhattan((mx, my), mid) <= 2:
                    fv += 600
            best_fv = max(best_fv, fv)
        sc += best_fv
        if not s["foods"] and s["length"] > s["opp_length"]:
            sc -= manhattan((mx, my), (s["W"]//2, s["H"]//2)) * 20
            sc += count_esc(mx, my, occ, s["W"], s["H"]) * 150
        sc += min(m.get("reach", 0), 60) * 5
        if best_fv < 300:
            sc += max(0, 8 - manhattan((mx, my), s["tail"])) * 20
        scores[m["dir"]] = sc
    return max(scores, key=scores.get)


def _bfs(sx, sy, tx, ty, blocked, W, H):
    """BFS real path distance (accounts for obstacles)."""
    if sx == tx and sy == ty:
        return 0
    visited = {(sx, sy)}
    q = deque([(sx, sy, 0)])
    while q:
        x, y, d = q.popleft()
        for dx, dy in DIRS.values():
            nx, ny = x + dx, y + dy
            if nx == tx and ny == ty:
                return d + 1
            if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in visited and (nx, ny) not in blocked:
                visited.add((nx, ny))
                q.append((nx, ny, d + 1))
    return 9999


def calc_v5(s):
    """V5 ULTRA: Adaptive strategy with advanced tactics.

    Improvements over base V5:
    - BFS real path for food racing (not manhattan)
    - 2-step lookahead: verify next moves are also safe
    - Direction-change rule exploitation for equal-length collisions
    - Opponent squeeze: reduce their escape routes
    - Wall corridor detection
    - Grapes always worth chasing (2x value confirmed)
    - Dynamic trapping in ALL phases
    """
    W, H = s["W"], s["H"]
    occ = build_occ(s)
    sm = safe_moves(s["head"], s["dir"], occ, W, H)
    if not sm:
        return fallback_dir(s["dir"])
    opp_n, opp_p = get_opp_next(s)
    cands, fb, need = flood_filter(sm, occ, s["head"], s["tail"], W, H, s["length"])

    # BFS blocked set (allow our tail to be passable)
    bfs_b = set(occ)
    bfs_b.discard(s["tail"])

    # Phase determination
    diff = s["length"] - s["opp_length"]
    if diff >= 2: phase = "stall"       # NEW: 길면 안 먹고 시간 끌기
    elif diff >= 1: phase = "pressure"
    elif diff <= -2: phase = "desperate"
    else: phase = "balanced"

    # Opponent's current escape routes (to compare squeeze effect)
    opp_esc_now = 0
    if s["opp_head"]:
        opp_esc_now = count_esc(s["opp_head"][0], s["opp_head"][1], occ, W, H)

    scores = {}
    for m in cands:
        sc = 0.0
        mx, my = m["x"], m["y"]

        # ====== A. ESCAPE ROUTES ======
        esc = count_esc(mx, my, occ, W, H)
        esc_w = {
            "stall": 150, "pressure": 90,
            "balanced": 80, "desperate": 70
        }[phase]
        sc += esc * esc_w

        # ====== B. 2-STEP LOOKAHEAD ======
        # Check: after moving here, how many of the NEXT moves are also safe?
        occ2 = set(occ)
        occ2.add(s["head"])  # our old head is now body
        occ2.discard(s["tail"])  # tail moves
        next_safe = 0
        for dx, dy in DIRS.values():
            nx, ny = mx + dx, my + dy
            if in_bounds(nx, ny, W, H) and (nx, ny) not in occ2:
                # Check that this 2nd step also has exits
                esc2 = sum(1 for dx2, dy2 in DIRS.values()
                           if in_bounds(nx+dx2, ny+dy2, W, H)
                           and (nx+dx2, ny+dy2) not in occ2
                           and (nx+dx2, ny+dy2) != (mx, my))
                if esc2 >= 1:
                    next_safe += 1
        sc += next_safe * 40
        # PENALTY if ALL next moves are dead ends
        if next_safe == 0 and esc > 0:
            sc -= 500

        # ====== C. WALL AWARENESS ======
        edge = min(mx, W-1-mx, my, H-1-my)
        if edge == 0:
            sc -= 180
            # Wall corridor detection: moving parallel to wall is dangerous
            if m["dir"] in ("up", "down") and (mx == 0 or mx == W-1):
                sc -= 100  # trapped along vertical wall
            elif m["dir"] in ("left", "right") and (my == 0 or my == H-1):
                sc -= 100  # trapped along horizontal wall
        elif edge == 1:
            sc -= 60
        else:
            sc += edge * 12

        # ====== D. REACHABLE SPACE ======
        reach = m.get("reach", 0)
        space_w = {"stall": 12, "pressure": 6, "balanced": 5, "desperate": 4}[phase]
        sc += min(reach, 80) * space_w

        # ====== E. HEAD-ON COLLISION ======
        if (mx, my) in opp_n:
            if diff >= 2:
                # Much longer: KILL
                sc += 6000 if opp_p and (mx, my) == opp_p else 2000
            elif diff == 1:
                # Slightly longer: worth it on predicted tile
                sc += 3000 if opp_p and (mx, my) == opp_p else 800
            elif diff == 0:
                # EQUAL LENGTH: "last direction change loses" rule!
                # If we DON'T change direction, we have advantage
                if m["dir"] == s["dir"]:
                    # We're going straight = opponent changed last = WE WIN
                    sc += 1500
                else:
                    # We changed direction = we might lose
                    sc -= 6000
            else:
                # Shorter: AVOID
                sc -= 15000

        # ====== F. FOOD TARGETING (BFS real path) ======
        best_fv = 0
        for f in s["foods"]:
            fx, fy = f["x"], f["y"]
            ft = f.get("type", "apple")
            lt = f.get("lifetime")

            # BFS real distance from candidate position
            my_bfs = _bfs(mx, my, fx, fy, bfs_b, W, H)
            # Manhattan for opponent (good enough estimate)
            od = manhattan(s["opp_head"], (fx, fy)) if s["opp_head"] else 999
            hd = manhattan(s["head"], (fx, fy))

            # Skip expired grapes
            if ft == "grapes" and lt is not None and lt < my_bfs + 1:
                continue

            # Grape = 2 points, Apple = 1 point
            grape = (ft == "grapes")
            fv = 0

            # Direct capture (landing on food THIS tick)
            if mx == fx and my == fy:
                fv = 5000 if grape else 2000
                best_fv = max(best_fv, fv)
                continue

            if phase == "stall":
                # STALL: 시간 끌기! 음식 AVOID (포도만 예외)
                if grape:
                    # 포도는 먹으면 차이가 +2 더 벌어져서 유리
                    if hd <= od:
                        fv = 3000 - my_bfs * 40
                    else:
                        fv = 1000 - my_bfs * 60
                else:
                    # 사과는 오히려 AVOID! 가까이 가지 마
                    if my_bfs <= 2:
                        fv = -1500  # 사과 근처 가면 페널티
                    else:
                        fv = 0

            elif phase == "pressure":
                if grape:
                    fv = 4500 - my_bfs * 35 if hd <= od else 2500 - my_bfs * 50
                elif hd < od:
                    fv = 1500 - my_bfs * 35
                elif hd == od:
                    fv = 800 - my_bfs * 40

            elif phase == "desperate":
                # EAT EVERYTHING - use BFS distance for accuracy
                if grape:
                    fv = 6000 - my_bfs * 30
                else:
                    fv = 2500 - my_bfs * 25

            else:  # balanced
                if grape:
                    # Grapes ALWAYS worth chasing
                    if hd <= od:
                        fv = 5000 - my_bfs * 35
                    else:
                        fv = 3000 - my_bfs * 50
                elif hd <= od:
                    fv = 1500 - my_bfs * 35
                elif hd == od + 1 and my_bfs <= 5:
                    fv = 600 - my_bfs * 40

            best_fv = max(best_fv, fv)
        sc += best_fv

        # ====== G. OPPONENT SQUEEZE ======
        # Try to reduce opponent's escape routes
        if s["opp_head"]:
            occ_after = set(occ)
            occ_after.add((mx, my))
            opp_esc_after = count_esc(
                s["opp_head"][0], s["opp_head"][1], occ_after, W, H)
            squeeze = opp_esc_now - opp_esc_after
            if squeeze > 0:
                sq_w = {"stall": 200, "pressure": 150,
                        "balanced": 80, "desperate": 30}[phase]
                sc += squeeze * sq_w
            # Bonus if opponent has 0 or 1 escape after our move
            if opp_esc_after <= 1 and reach > need:
                sc += 1500

        # ====== H. TRAPPING (all phases, weighted) ======
        if s["opp_head"] and reach > need:
            ob = set(fb)
            ob.add((mx, my))
            os_ = flood_fill(s["opp_head"][0], s["opp_head"][1], ob, W, H, 60)
            space_adv = reach - os_
            trap_w = {"stall": 50, "pressure": 30,
                      "balanced": 15, "desperate": 5}[phase]
            sc += space_adv * trap_w
            if os_ < s["opp_length"] + 2:
                sc += 8000  # lethal trap
            elif os_ < s["opp_length"] + 5:
                sc += 3000
            elif os_ < 15:
                sc += 1000

        # ====== I. TAIL CHASING (safe fallback) ======
        if best_fv < 300:
            td = manhattan((mx, my), s["tail"])
            sc += max(0, 10 - td) * 25

        # ====== J. STALEMATE / STALL PLAY ======
        cx, cy = W // 2, H // 2
        if phase == "stall":
            # STALL MODE: 중앙 장악 + 생존 극대화 + 시간 끌기
            sc -= manhattan((mx, my), (cx, cy)) * 35
            sc += esc * 250
            # Tail chasing for safe circular movement
            td = manhattan((mx, my), s["tail"])
            sc += max(0, 10 - td) * 30
        elif not s["foods"]:
            if s["length"] > s["opp_length"]:
                sc -= manhattan((mx, my), (cx, cy)) * 30
                sc += esc * 200
            elif s["length"] < s["opp_length"]:
                sc -= manhattan((mx, my), (cx, cy)) * 15

        # ====== K. OPPONENT CUT-OFF ======
        if s["opp_head"] and s["foods"]:
            for f in s["foods"]:
                fx, fy = f["x"], f["y"]
                md = manhattan((mx, my), (fx, fy))
                od2 = manhattan(s["opp_head"], (fx, fy))
                if md < od2 and od2 <= 8:
                    cutoff_w = {"stall": 100, "pressure": 250,
                                "balanced": 150, "desperate": 50}[phase]
                    sc += cutoff_w
                    break

        scores[m["dir"]] = sc
    return max(scores, key=scores.get)


CALC = {1: calc_v1, 2: calc_v2, 3: calc_v3, 4: calc_v4, 5: calc_v5}


# =========================================================================
#  Bot class
# =========================================================================

class MyBot:
    def __init__(self, server_url, name, strategy_num):
        self.server_url = server_url
        self.name = name
        self.strategy = strategy_num
        self.calc_fn = CALC[strategy_num]
        self.player_id = None
        self.game_state = None
        self.running = False
        self.room_id = None
        self.grid_width = 15
        self.grid_height = 15

    def log(self, msg):
        print(msg.encode("ascii", errors="replace").decode("ascii"))

    async def wait_for_server(self):
        import aiohttp
        base = self.server_url.rstrip("/")
        if base.endswith("/ws"): base = base[:-3]
        http = base.replace("ws://", "http://").replace("wss://", "https://")
        while True:
            try:
                async with aiohttp.ClientSession() as ses:
                    async with ses.get(http + "/status") as r:
                        if r.status == 200:
                            self.log("Server reachable - joining lobby...")
                            return
            except Exception as e:
                self.log("Waiting for server...")
            await asyncio.sleep(3)

    async def connect(self):
        await self.wait_for_server()
        base = self.server_url.rstrip("/")
        if base.endswith("/ws"): base = base[:-3]
        url = base + "/ws/join"
        self.ws = await websockets.connect(url)
        self.log("Connected!")
        await self.ws.send(json.dumps({"action": "join", "name": self.name}))

    async def play(self):
        while True:
            try:
                await self.connect()
                self.running = True
                while self.running:
                    data = json.loads(await self.ws.recv())
                    await self.handle(data)
            except websockets.ConnectionClosed:
                self.log("Disconnected.")
            except Exception as e:
                self.log("Error: %s" % e)
            finally:
                self.running = False
                try: await self.ws.close()
                except: pass
            self.log("Reconnecting in 3s...")
            await asyncio.sleep(3)

    async def handle(self, data):
        t = data.get("type")
        if t == "error":
            self.log("Error: %s" % data.get("message")); self.running = False
        elif t == "lobby_joined":
            self.log("In lobby as '%s'" % data.get("name", self.name))
        elif t == "lobby_update":
            pass
        elif t in ("lobby_left", "lobby_kicked"):
            self.running = False
        elif t == "joined":
            self.player_id = data.get("player_id")
            self.room_id = data.get("room_id")
            self.log("Arena %s, Player %s" % (self.room_id, self.player_id))
            await self.ws.send(json.dumps({"action":"ready","mode":"two_player","name":self.name}))
        elif t == "match_assigned":
            self.room_id = data.get("room_id")
            self.player_id = data.get("player_id")
            self.game_state = None
            self.log("Next round vs %s" % data.get("opponent", "?"))
            await self.ws.send(json.dumps({"action":"ready","name":self.name}))
        elif t == "state":
            self.game_state = data.get("game")
            g = self.game_state.get("grid", {})
            if g:
                self.grid_width = g.get("width", self.grid_width)
                self.grid_height = g.get("height", self.grid_height)
            if self.game_state and self.game_state.get("running"):
                s = parse_state(self.game_state, self.player_id, self.grid_width, self.grid_height)
                if s:
                    d = self.calc_fn(s)
                    if d:
                        await self.ws.send(json.dumps({"action":"move","direction":d}))
        elif t == "start":
            self.log("Game started!")
        elif t == "gameover":
            w = data.get("winner")
            mw = data.get("wins",{}).get(str(self.player_id),0)
            ow = data.get("wins",{}).get(str(3-self.player_id),0)
            ptw = data.get("points_to_win",3)
            r = "WON" if w == self.player_id else ("LOST" if w else "DRAW")
            self.log("%s! %s-%s (first to %s)" % (r, mw, ow, ptw))
            await self.ws.send(json.dumps({"action":"ready","name":self.name}))
        elif t == "match_complete":
            wid = data.get("winner",{}).get("player_id")
            if wid == self.player_id:
                self.log("MATCH WON! Next round...")
            else:
                self.log("Match lost. Eliminated.")
                self.running = False
        elif t == "competition_complete":
            self.log("Champion: %s" % data.get("champion",{}).get("name","?"))
            self.running = False
        elif t == "waiting":
            self.log("Waiting...")


def main():
    parser = argparse.ArgumentParser(description="tommy_jhp CopperHead Bot")
    parser.add_argument("strategy", nargs="?", type=int, help="Strategy 1-5")
    parser.add_argument("--name", "-n", default=None)
    parser.add_argument("--server", "-s", default=SERVER)
    args = parser.parse_args()

    strat = args.strategy
    if strat is None:
        strat = pick_strategy()
    if strat not in STRATEGIES:
        print("1~5 중에 골라주세요!")
        return

    sname, sdesc = STRATEGIES[strat]
    bot_name = args.name or ("tommy_jhp_%s" % sname)

    print()
    print("  Bot: %s" % bot_name)
    print("  Strategy: %s - %s" % (sname, sdesc))
    print("  Server: %s" % args.server)
    print()

    bot = MyBot(args.server, bot_name, strat)
    asyncio.run(bot.play())


if __name__ == "__main__":
    main()
