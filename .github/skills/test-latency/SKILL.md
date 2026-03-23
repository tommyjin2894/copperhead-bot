---
name: test-latency
description: Test network latency between the bot's machine and a CopperHead server to diagnose bot performance issues.
---

# Test Server Latency

Use this skill when the user asks to test latency, check connection speed, or diagnose why their bot is crashing into walls.

Examples:
- "test latency"
- "check latency to the server"
- "why is my bot hitting walls"
- "test connection speed"
- "measure ping to server"
- "is my connection fast enough"

## Goal

Measure the HTTP round-trip latency between the bot's machine and a CopperHead server, then compare it to the server's tick rate to determine if latency could cause gameplay issues.

## Procedure

1. Determine the server URL. Ask the user if not provided. Accept WebSocket URLs (`ws://` or `wss://`) or HTTP URLs.

2. Convert the URL to HTTP format for testing:

   ```python
   # ws://host:port/ws/ → http://host:port
   # wss://host:port/ws/ → https://host:port
   ```

3. Run a latency test using Python. Send 10 HTTP requests to the server's `/status` endpoint and measure round-trip times:

   ```powershell
   python -c "
   import time, urllib.request, json, ssl

   url = '<HTTP_URL>/status'
   ctx = ssl.create_default_context()

   times = []
   for i in range(10):
       start = time.perf_counter()
       try:
           req = urllib.request.urlopen(url, timeout=5, context=ctx)
           data = req.read()
           elapsed = (time.perf_counter() - start) * 1000
           times.append(elapsed)
       except Exception as e:
           print(f'  Request {i+1}: FAILED ({e})')

   if times:
       avg = sum(times) / len(times)
       mn = min(times)
       mx = max(times)
       print(f'Latency to server ({url}):')
       print(f'  Requests:  {len(times)}/10 succeeded')
       print(f'  Min:       {mn:.0f}ms')
       print(f'  Max:       {mx:.0f}ms')
       print(f'  Average:   {avg:.0f}ms')
       print()

       # Parse tick rate from server status
       try:
           data_json = json.loads(data)
           tick_ms = data_json.get('speed', 0.15) * 1000
           print(f'Server tick rate: {tick_ms:.0f}ms')
           print()
           if avg > tick_ms:
               print(f'WARNING: Average latency ({avg:.0f}ms) exceeds tick rate ({tick_ms:.0f}ms).')
               print(f'Your bot will miss ticks. Moves will arrive too late.')
               print(f'Fix: Run your bot closer to the server, or increase the')
               print(f'     speed value in server-settings.json (e.g. 0.3 or higher).')
           elif avg > tick_ms * 0.5:
               print(f'CAUTION: Average latency ({avg:.0f}ms) is more than half the tick rate ({tick_ms:.0f}ms).')
               print(f'Your bot may occasionally miss ticks during network spikes.')
               print(f'Consider running closer to the server for best results.')
           else:
               print(f'OK: Average latency ({avg:.0f}ms) is well within the tick rate ({tick_ms:.0f}ms).')
               print(f'Your bot should be able to respond in time.')
       except Exception:
           pass
   else:
       print('All requests failed. Check the server URL and try again.')
   "
   ```

4. Report the results to the user. If latency is problematic, suggest:
   - Running the bot in the same Codespace or cloud region as the server
   - Increasing the server's `speed` setting in `server-settings.json`

## Important notes

- This test uses only standard library modules (no pip install needed).
- The test sends 10 sequential HTTP requests — it takes a few seconds to complete.
- A good rule of thumb: average latency should be less than half the server's tick rate for reliable gameplay.
