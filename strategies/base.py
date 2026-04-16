"""
Base bot class with connection/message handling.
All strategy variants inherit from this.
"""
import asyncio
import json
import websockets
from collections import deque


class BaseBot:
    """Shared connection logic. Subclasses override calculate_move()."""

    def __init__(self, server_url, name="BaseBot"):
        self.server_url = server_url
        self.name = name
        self.player_id = None
        self.game_state = None
        self.running = False
        self.room_id = None
        self.grid_width = 15
        self.grid_height = 15
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.quiet = False

    def log(self, msg):
        if not self.quiet:
            print("[%s] %s" % (self.name, msg))

    async def wait_for_server(self):
        import aiohttp
        base = self.server_url.rstrip("/")
        if base.endswith("/ws"):
            base = base[:-3]
        http = base.replace("ws://", "http://").replace("wss://", "https://")
        while True:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(http + "/status") as r:
                        if r.status == 200:
                            return True
            except Exception:
                pass
            await asyncio.sleep(2)

    async def connect(self):
        await self.wait_for_server()
        base = self.server_url.rstrip("/")
        if base.endswith("/ws"):
            base = base[:-3]
        url = base + "/ws/join"
        try:
            self.ws = await websockets.connect(url)
            await self.ws.send(json.dumps({"action": "join", "name": self.name}))
            return True
        except Exception as e:
            self.log("Connection failed: %s" % e)
            return False

    async def play(self):
        if not await self.connect():
            return
        self.running = True
        try:
            while self.running:
                msg = await self.ws.recv()
                data = json.loads(msg)
                await self.handle_message(data)
        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            self.log("Error: %s" % e)
        finally:
            self.running = False
            try:
                await self.ws.close()
            except Exception:
                pass

    async def handle_message(self, data):
        t = data.get("type")

        if t == "error":
            self.log("Error: %s" % data.get("message"))
            self.running = False

        elif t == "lobby_joined":
            self.log("In lobby")

        elif t == "lobby_update":
            pass

        elif t in ("lobby_left", "lobby_kicked"):
            self.running = False

        elif t == "joined":
            self.player_id = data.get("player_id")
            self.room_id = data.get("room_id")
            await self.ws.send(json.dumps({
                "action": "ready", "mode": "two_player", "name": self.name
            }))

        elif t == "match_assigned":
            self.room_id = data.get("room_id")
            self.player_id = data.get("player_id")
            self.game_state = None
            await self.ws.send(json.dumps({"action": "ready", "name": self.name}))

        elif t == "state":
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

        elif t == "start":
            pass

        elif t == "gameover":
            w = data.get("winner")
            if w == self.player_id:
                self.wins += 1
            elif w:
                self.losses += 1
            else:
                self.draws += 1
            await self.ws.send(json.dumps({"action": "ready", "name": self.name}))

        elif t == "match_complete":
            wid = data.get("winner", {}).get("player_id")
            if wid != self.player_id:
                self.running = False

        elif t == "competition_complete":
            champ = data.get("champion", {}).get("name", "?")
            self.log("Champion: %s | My record: %dW-%dL-%dD" % (
                champ, self.wins, self.losses, self.draws))
            self.running = False

        elif t == "waiting":
            pass

    def calculate_move(self):
        raise NotImplementedError

    # === SHARED UTILITIES ===

    def get_state(self):
        """Parse game state into convenient variables."""
        snakes = self.game_state.get("snakes", {})
        me = snakes.get(str(self.player_id))
        if not me or not me.get("body"):
            return None

        oid = str(3 - self.player_id)
        opp = snakes.get(oid)

        state = {
            "head": (me["body"][0][0], me["body"][0][1]),
            "body": [(s[0], s[1]) for s in me["body"]],
            "length": len(me["body"]),
            "dir": me.get("direction", "right"),
            "tail": (me["body"][-1][0], me["body"][-1][1]),
            "foods": self.game_state.get("foods", []),
            "opp_head": None,
            "opp_body": [],
            "opp_length": 0,
            "opp_dir": None,
            "opp_tail": None,
            "W": self.grid_width,
            "H": self.grid_height,
        }

        if opp and opp.get("body") and opp.get("alive", True):
            state["opp_head"] = (opp["body"][0][0], opp["body"][0][1])
            state["opp_body"] = [(s[0], s[1]) for s in opp["body"]]
            state["opp_length"] = len(opp["body"])
            state["opp_dir"] = opp.get("direction")
            state["opp_tail"] = (opp["body"][-1][0], opp["body"][-1][1])

        return state

    def build_occupied(self, s, exclude_my_tail=True, include_opp_tail=True):
        """Build set of occupied tiles."""
        occ = set()
        body = s["body"][:-1] if exclude_my_tail else s["body"]
        for seg in body:
            occ.add(seg)
        opp_body = s["opp_body"] if include_opp_tail else s["opp_body"][:-1]
        for seg in opp_body:
            occ.add(seg)
        return occ

    def get_opp_real_next(self, s):
        """Opponent's realistic next positions (exclude reverse)."""
        DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        OPP = {"up": "down", "down": "up", "left": "right", "right": "left"}
        result = set()
        predicted = None
        oh = s["opp_head"]
        od = s["opp_dir"]
        if oh and od:
            rev = OPP.get(od)
            for d, (dx, dy) in DIRS.items():
                if d == rev:
                    continue
                nx, ny = oh[0] + dx, oh[1] + dy
                if 0 <= nx < s["W"] and 0 <= ny < s["H"]:
                    result.add((nx, ny))
            pdx, pdy = DIRS[od]
            predicted = (oh[0] + pdx, oh[1] + pdy)
        return result, predicted

    def flood_fill(self, sx, sy, blocked, W, H, limit=225):
        DIRS_V = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        if (sx, sy) in blocked:
            return 0
        visited = set()
        visited.add((sx, sy))
        q = deque()
        q.append((sx, sy))
        count = 0
        while q:
            x, y = q.popleft()
            count += 1
            if count >= limit:
                return count
            for dx, dy in DIRS_V:
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in visited and (nx, ny) not in blocked:
                    visited.add((nx, ny))
                    q.append((nx, ny))
        return count

    def get_safe_moves(self, head, cur_dir, occupied, W, H):
        DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        OPP = {"up": "down", "down": "up", "left": "right", "right": "left"}
        moves = []
        for d, (dx, dy) in DIRS.items():
            if d == OPP.get(cur_dir):
                continue
            nx, ny = head[0] + dx, head[1] + dy
            if 0 <= nx < W and 0 <= ny < H and (nx, ny) not in occupied:
                moves.append({"dir": d, "x": nx, "y": ny})
        return moves

    def manhattan(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
