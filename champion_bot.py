#!/usr/bin/env python3
"""
Champion Bot - Ultimate CopperHead Snake AI designed to WIN tournaments.

Combines the best strategies from all existing bots with advanced techniques:
- BFS flood fill to never enter dead-end spaces
- A* style pathfinding for optimal food routes
- Aggressive grape targeting (double value: +1 self, -1 opponent)
- Smart head-on collision seeking when longer
- Opponent cut-off positioning
- Tail chasing as safe fallback
"""

import asyncio
import json
import argparse
import random
import websockets
from collections import deque


GAME_SERVER = "wss://copperhead-server.politesmoke-80c82ad7.eastasia.azurecontainerapps.io/ws/"
BOT_NAME = "tommy_jhp"
BOT_VERSION = "1.0"


class ChampionBot:
    def __init__(self, server_url: str, name: str = None):
        self.server_url = server_url
        self.name = name or BOT_NAME
        self.player_id = None
        self.game_state = None
        self.running = False
        self.room_id = None
        self.grid_width = 15
        self.grid_height = 15
        self.prev_opp_dirs = []  # track opponent direction history

    def log(self, msg: str):
        print(msg.encode("ascii", errors="replace").decode("ascii"))

    async def wait_for_server(self):
        import aiohttp
        base_url = self.server_url.rstrip("/")
        if base_url.endswith("/ws"):
            base_url = base_url[:-3]
        http_url = base_url.replace("ws://", "http://").replace("wss://", "https://")
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{http_url}/status") as resp:
                        if resp.status == 200:
                            self.log("Server reachable - joining lobby...")
                            return True
            except Exception as e:
                self.log(f"Waiting for server: {e}")
            await asyncio.sleep(3)

    async def connect(self):
        await self.wait_for_server()
        base_url = self.server_url.rstrip("/")
        if base_url.endswith("/ws"):
            base_url = base_url[:-3]
        url = f"{base_url}/ws/join"
        try:
            self.log(f"Connecting to {url}...")
            self.ws = await websockets.connect(url)
            self.log("Connected!")
            await self.ws.send(json.dumps({"action": "join", "name": self.name}))
            return True
        except Exception as e:
            self.log(f"Connection failed: {e}")
            return False

    async def play(self):
        if not await self.connect():
            return
        self.running = True
        try:
            while self.running:
                message = await self.ws.recv()
                data = json.loads(message)
                await self.handle_message(data)
        except websockets.ConnectionClosed:
            self.log("Disconnected.")
        except Exception as e:
            self.log(f"Error: {e}")
        finally:
            self.running = False
            try:
                await self.ws.close()
            except Exception:
                pass

    async def handle_message(self, data: dict):
        msg_type = data.get("type")

        if msg_type == "error":
            self.log(f"Error: {data.get('message')}")
            self.running = False

        elif msg_type == "lobby_joined":
            self.log(f"In lobby as '{data.get('name', self.name)}'")

        elif msg_type == "lobby_update":
            pass

        elif msg_type in ("lobby_left", "lobby_kicked"):
            self.log("Removed from lobby.")
            self.running = False

        elif msg_type == "joined":
            self.player_id = data.get("player_id")
            self.room_id = data.get("room_id")
            self.log(f"Joined Arena {self.room_id} as Player {self.player_id}")
            await self.ws.send(json.dumps({
                "action": "ready", "mode": "two_player", "name": self.name
            }))

        elif msg_type == "match_assigned":
            self.room_id = data.get("room_id")
            self.player_id = data.get("player_id")
            self.game_state = None
            self.prev_opp_dirs = []
            opponent = data.get("opponent", "?")
            self.log(f"Round: Arena {self.room_id} vs {opponent}")
            await self.ws.send(json.dumps({"action": "ready", "name": self.name}))

        elif msg_type == "state":
            self.game_state = data.get("game")
            grid = self.game_state.get("grid", {})
            if grid:
                self.grid_width = grid.get("width", self.grid_width)
                self.grid_height = grid.get("height", self.grid_height)
            if self.game_state and self.game_state.get("running"):
                direction = self.calculate_move()
                if direction:
                    await self.ws.send(json.dumps({
                        "action": "move", "direction": direction
                    }))

        elif msg_type == "start":
            self.log("Game started!")
            self.prev_opp_dirs = []

        elif msg_type == "gameover":
            winner = data.get("winner")
            my_wins = data.get("wins", {}).get(str(self.player_id), 0)
            opp_id = 3 - self.player_id
            opp_wins = data.get("wins", {}).get(str(opp_id), 0)
            ptw = data.get("points_to_win", 3)
            result = "WON" if winner == self.player_id else ("LOST" if winner else "DRAW")
            self.log(f"{result}! Score: {my_wins}-{opp_wins} (first to {ptw})")
            await self.ws.send(json.dumps({"action": "ready", "name": self.name}))

        elif msg_type == "match_complete":
            winner_id = data.get("winner", {}).get("player_id")
            if winner_id == self.player_id:
                self.log("MATCH WON! Advancing...")
            else:
                self.log(f"Match lost to {data.get('winner', {}).get('name')}. Eliminated.")
                self.running = False

        elif msg_type == "competition_complete":
            champion = data.get("champion", {}).get("name", "?")
            self.log(f"Tournament over! Champion: {champion}")
            self.running = False

        elif msg_type == "waiting":
            self.log("Waiting...")

    # =========================================================================
    #  CORE AI
    # =========================================================================

    def calculate_move(self) -> str | None:
        if not self.game_state:
            return None

        snakes = self.game_state.get("snakes", {})
        my_snake = snakes.get(str(self.player_id))
        if not my_snake or not my_snake.get("body"):
            return None

        head = tuple(my_snake["body"][0])
        my_body = [tuple(s) for s in my_snake["body"]]
        my_length = len(my_body)
        current_dir = my_snake.get("direction", "right")
        foods = self.game_state.get("foods", [])

        # Opponent info
        opp_id = str(3 - self.player_id)
        opp_snake = snakes.get(opp_id)
        opp_head = None
        opp_body = []
        opp_length = 0
        opp_dir = None
        if opp_snake and opp_snake.get("body"):
            opp_head = tuple(opp_snake["body"][0])
            opp_body = [tuple(s) for s in opp_snake["body"]]
            opp_length = len(opp_body)
            opp_dir = opp_snake.get("direction")
            self.prev_opp_dirs.append(opp_dir)
            if len(self.prev_opp_dirs) > 20:
                self.prev_opp_dirs = self.prev_opp_dirs[-20:]

        DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        OPPOSITES = {"up": "down", "down": "up", "left": "right", "right": "left"}

        # Build occupied set (exclude tails - they'll move)
        occupied = set()
        my_tail = tuple(my_body[-1])
        for seg in my_body[:-1]:
            occupied.add(seg)
        if opp_snake and opp_body:
            # Keep opponent tail as dangerous (they might eat)
            for seg in opp_body:
                occupied.add(seg)

        # Opponent's possible next positions (all 4 adjacent to their head)
        opp_possible_next = set()
        opp_predicted_next = None
        if opp_head and opp_dir:
            dx, dy = DIRS.get(opp_dir, (0, 0))
            opp_predicted_next = (opp_head[0] + dx, opp_head[1] + dy)
            for ddx, ddy in DIRS.values():
                nx, ny = opp_head[0] + ddx, opp_head[1] + ddy
                if 0 <= nx < self.grid_width and 0 <= ny < self.grid_height:
                    opp_possible_next.add((nx, ny))

        def in_bounds(x, y):
            return 0 <= x < self.grid_width and 0 <= y < self.grid_height

        def is_safe(x, y):
            return in_bounds(x, y) and (x, y) not in occupied

        def is_strict_safe(x, y):
            """Safe AND not adjacent to opponent head (avoid head-on risk)."""
            return is_safe(x, y) and (x, y) not in opp_possible_next

        # Flood fill: count reachable tiles from (sx, sy)
        def flood_fill(sx, sy, blocked, limit=300):
            if (sx, sy) in blocked:
                return 0
            visited = {(sx, sy)}
            q = deque([(sx, sy)])
            count = 0
            while q:
                x, y = q.popleft()
                count += 1
                if count >= limit:
                    return count
                for ddx, ddy in DIRS.values():
                    nx, ny = x + ddx, y + ddy
                    if in_bounds(nx, ny) and (nx, ny) not in visited and (nx, ny) not in blocked:
                        visited.add((nx, ny))
                        q.append((nx, ny))
            return count

        # BFS shortest path length from (sx,sy) to (tx,ty) avoiding blocked
        def bfs_dist(sx, sy, tx, ty, blocked):
            if (sx, sy) == (tx, ty):
                return 0
            visited = {(sx, sy)}
            q = deque([(sx, sy, 0)])
            while q:
                x, y, d = q.popleft()
                for ddx, ddy in DIRS.values():
                    nx, ny = x + ddx, y + ddy
                    if (nx, ny) == (tx, ty):
                        return d + 1
                    if in_bounds(nx, ny) and (nx, ny) not in visited and (nx, ny) not in blocked:
                        visited.add((nx, ny))
                        q.append((nx, ny, d + 1))
            return float('inf')

        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        # Get all non-reversing safe moves
        safe_moves = []
        for direction, (dx, dy) in DIRS.items():
            if direction == OPPOSITES.get(current_dir):
                continue
            nx, ny = head[0] + dx, head[1] + dy
            if is_safe(nx, ny):
                safe_moves.append({"dir": direction, "x": nx, "y": ny})

        if not safe_moves:
            # Doomed - try any non-reversing direction
            for d in DIRS:
                if d != OPPOSITES.get(current_dir):
                    return d
            return current_dir

        # === PHASE 1: Filter by flood fill (SURVIVAL) ===
        # Never enter a space with fewer reachable tiles than our body length
        # Use occupied set minus our tail (it'll move) for reachability
        flood_blocked = set(occupied)
        flood_blocked.discard(my_tail)

        move_scores = {}
        roomy_moves = []
        min_needed = max(my_length, 6)  # need at least body length or 6 tiles

        for move in safe_moves:
            blocked_for_flood = set(flood_blocked)
            blocked_for_flood.add(head)  # our old head position is now body
            reachable = flood_fill(move["x"], move["y"], blocked_for_flood, min_needed + 1)
            move["reachable"] = reachable
            if reachable >= min_needed:
                roomy_moves.append(move)

        candidates = roomy_moves if roomy_moves else safe_moves

        # === PHASE 2: Score each candidate ===
        for move in candidates:
            score = 0.0
            mx, my_ = move["x"], move["y"]

            # --- 2a. Escape routes ---
            escape = 0
            for ddx, ddy in DIRS.values():
                if is_safe(mx + ddx, my_ + ddy):
                    escape += 1
            score += escape * 60

            # --- 2b. Wall avoidance (important on 15x15) ---
            edge_dist = min(mx, self.grid_width - 1 - mx, my_, self.grid_height - 1 - my_)
            if edge_dist == 0:
                score -= 80
            elif edge_dist == 1:
                score -= 20
            else:
                score += edge_dist * 8

            # --- 2c. Avoid opponent's possible next tiles ---
            if (mx, my_) in opp_possible_next:
                if my_length > opp_length + 1:
                    # We're significantly longer - seek head-on collision!
                    if (mx, my_) == opp_predicted_next:
                        score += 2500
                    else:
                        score += 500
                elif my_length > opp_length:
                    # Slightly longer - cautious aggression
                    if (mx, my_) == opp_predicted_next:
                        score += 800
                    else:
                        score -= 200
                else:
                    # Equal or shorter - AVOID
                    score -= 8000

            # --- 2d. Food targeting ---
            # Priority: grapes >> food we're closer to than opponent
            best_food_score = 0

            for food in foods:
                fx, fy = food["x"], food["y"]
                ftype = food.get("type", "apple")
                lifetime = food.get("lifetime")

                my_dist = manhattan((mx, my_), (fx, fy))
                my_head_dist = manhattan(head, (fx, fy))
                opp_dist = manhattan(opp_head, (fx, fy)) if opp_head else float('inf')

                # Use BFS for actual path distance (more accurate)
                my_bfs = bfs_dist(mx, my_, fx, fy, flood_blocked)

                # Skip expired grapes that are far away
                if ftype == "grapes" and lifetime is not None and lifetime < 5 and my_dist > 8:
                    continue

                food_value = 0

                if ftype == "grapes":
                    # Grapes are HUGE value: +1 length, -1 opponent
                    # Effectively worth 2 points of advantage
                    base_value = 3000
                    if my_head_dist < opp_dist:
                        food_value = base_value - my_bfs * 40
                    elif my_head_dist == opp_dist:
                        food_value = base_value * 0.6 - my_bfs * 40
                    else:
                        # Opponent closer, but still worth going for if close
                        food_value = base_value * 0.3 - my_bfs * 60
                else:
                    # Apple
                    base_value = 1000
                    if my_head_dist < opp_dist:
                        # We're closer - go for it
                        food_value = base_value - my_bfs * 30
                    elif my_head_dist == opp_dist:
                        food_value = base_value * 0.4 - my_bfs * 30
                    else:
                        # Opponent closer - deprioritize unless very close
                        if my_dist <= 3:
                            food_value = base_value * 0.2 - my_bfs * 50
                        else:
                            food_value = -my_bfs * 10

                # Landing directly on food
                if mx == fx and my_ == fy:
                    food_value += 1500 if ftype == "grapes" else 800

                best_food_score = max(best_food_score, food_value)

            score += best_food_score

            # --- 2e. Opponent cut-off strategy ---
            # Try to position between opponent and the nearest food
            if opp_head and foods:
                nearest_food_to_opp = min(foods,
                    key=lambda f: manhattan(opp_head, (f["x"], f["y"])))
                nfx, nfy = nearest_food_to_opp["x"], nearest_food_to_opp["y"]
                # Our distance from that food vs opponent's
                my_d = manhattan((mx, my_), (nfx, nfy))
                opp_d = manhattan(opp_head, (nfx, nfy))
                if my_d < opp_d:
                    # We're between opponent and food - good blocking position
                    score += 150

            # --- 2f. Space dominance ---
            # On a 15x15 grid, controlling more space is critical
            reachable = move.get("reachable", 0)
            score += min(reachable, 50) * 3

            # --- 2g. Stalemate awareness ---
            # If no food and we need to survive, prefer center
            if not foods:
                center_x = self.grid_width // 2
                center_y = self.grid_height // 2
                center_dist = manhattan((mx, my_), (center_x, center_y))
                score -= center_dist * 15
                # Length matters in stalemate - don't rush into danger
                score += escape * 100

            move_scores[move["dir"]] = score

        # Pick the best scoring move
        best_dir = max(move_scores, key=move_scores.get)
        return best_dir


async def main():
    parser = argparse.ArgumentParser(description="Champion Bot")
    parser.add_argument("--server", "-s", default=GAME_SERVER,
                        help=f"Server URL (default: {GAME_SERVER})")
    parser.add_argument("--name", "-n", default=None,
                        help=f"Bot name (default: {BOT_NAME})")
    args = parser.parse_args()

    bot = ChampionBot(args.server, name=args.name)
    print(f"{bot.name} v{BOT_VERSION}")
    print(f"  Server: {args.server}")
    print()
    await bot.play()


if __name__ == "__main__":
    asyncio.run(main())
