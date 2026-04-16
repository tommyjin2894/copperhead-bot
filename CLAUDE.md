# CopperHead Bot Project - Team tommy_jhp

## Goal
CopperHead 뱀 게임 토너먼트에서 **우승**하는 AI 봇 개발.

## Project Structure
```
tommy-bot/
  mybot.py                  # 메인 봇 (토너먼트 제출용)
  run_bot.py                # 전략 봇 실행 래퍼
  arena.py                  # 봇 vs 봇 테스트 프레임워크
  tournament_online.sh      # 5개 봇 온라인 동시 실행
  tournament_local.sh       # 로컬 서버 + 봇 대결 자동화
  local_server_settings.json # 로컬 테스트용 서버 설정
  strategies/
    base.py                 # 공통 연결/메시지 처리 (BaseBot)
    v1_aggressive.py        # 전략1: 공격적 음식 수집 + 정면충돌
    v2_defensive.py         # 전략2: 생존 최우선 + 꼬리 추적
    v3_trapper.py           # 전략3: 상대를 벽/코너에 가두기
    v4_cutoff.py            # 전략4: 상대-음식 사이 차단
    v5_hybrid.py            # 전략5: 상황적응형 (길이에 따라 전환)
  results/                  # 테스트 결과 로그
```

## Server & Connection
- **Tournament Server**: `wss://copperhead-server.politesmoke-80c82ad7.eastasia.azurecontainerapps.io/ws/`
- **Local Test Server**: `ws://localhost:8765/ws/`
- **Server Code**: `../copperhead-server/main.py`
- **Latency**: ~150ms (East Asia Azure), 틱(250ms) 내 응답 가능
- **Python**: 3.9 (str | None 문법 사용 금지, Optional 사용)

## Tournament Settings (server-settings.json)
| Parameter | Value | Impact |
|-----------|-------|--------|
| grid_size | 15x15 | 좁음 - 벽 충돌 위험 높음, 공간 관리 중요 |
| speed | 0.25s | 4 ticks/sec |
| points_to_win | 3 | 3점 선승 |
| game-timeout | 30s | 30초 동안 아무도 안 먹으면 긴 뱀이 승리 |
| max_fruits | 5 | 최대 5개 과일 동시 존재 |
| fruit_interval | 8 | 8틱마다 새 과일 |
| apple propensity | 9 | 90% 확률 |
| grapes propensity | 1 | 10% 확률, lifetime 40틱 |

## Game Rules (Critical)
1. **이동**: 자동으로 현재 방향 직진, 역방향 전환 불가
2. **충돌**: 벽/뱀 몸에 부딪히면 사망 → 상대에게 1점
3. **정면충돌 (Head-to-Head)**:
   - 같은 칸 또는 교차 이동 시 발생
   - **긴 뱀 승리**
   - 같은 길이면 → **마지막에 방향 바꾼 쪽이 패배**
   - 둘 다 바꿨거나 안 바꿨으면 → 무승부
4. **과일**:
   - 사과: 길이 +1
   - 포도: 나 길이 +1, **상대 길이 -1** (2배 가치!)
5. **Stalemate**: 30초간 과일 미수집 → 긴 뱀 승리
6. **연속 무승부**: 3연속 무승부 → 랜덤으로 점수 부여
7. **연결 끊김 = 몰수패**

## WebSocket API
### Client → Server
| action | fields | when |
|--------|--------|------|
| join | name | 로비 입장 |
| ready | name (optional) | 게임 시작 준비 |
| move | direction (up/down/left/right) | 매 틱 |

### Server → Client (주요)
| type | 의미 | 필요 행동 |
|------|------|-----------|
| lobby_joined | 로비 입장 확인 | 대기 |
| match_assigned | 매치 배정 | ready 전송 |
| state | 매 틱 게임 상태 | calculate_move() 호출 → move 전송 |
| gameover | 게임 종료 | ready 전송 (다음 게임) |
| match_complete | 매치 종료 | 이기면 대기, 지면 종료 |
| competition_complete | 토너먼트 종료 | 종료 |

### Game State (state.game)
```json
{
  "running": true,
  "tick": 42,
  "grid": {"width": 15, "height": 15},
  "snakes": {
    "1": {
      "body": [[x,y], [x,y], ...],  // head = body[0]
      "direction": "right",
      "alive": true,
      "buff": "default"
    },
    "2": { ... }
  },
  "foods": [
    {"x": 5, "y": 10, "type": "apple", "lifetime": null},
    {"x": 3, "y": 7, "type": "grapes", "lifetime": 35}
  ]
}
```
- `(0,0)` = 좌상단, y 아래로 증가
- `body[0]` = 머리, `body[-1]` = 꼬리
- player_id는 "1" 또는 "2" (문자열 키)
- opponent_id = 3 - player_id

## Existing Bot Analysis (bot-library)
| Bot | Strategy | Weakness |
|-----|----------|----------|
| CopperBot | Score-based, food+escape | No flood fill, gets trapped |
| UltraBot | Safety-first + flood fill | Not aggressive, no cut-off |
| MurderBot | Grow to 5 → chase opponent | No flood fill, all body is "dangerous" |
| ShyBot | Stay short, harass | Loses stalemates (always short) |
| SleepySnake | Random wandering | Not competitive |

## Our Strategy Evolution
### v1 (mybot.py original): Basic scoring
- Lost to Eddie-bot 2-3
- Weakness: manhattan distance (not real path), no stalemate strategy

### v2 (mybot.py current): Enhanced
- BFS real path distance
- Opponent reverse excluded from danger zone
- Multi-fruit awareness
- Stalemate strategy
- Won tournament once (3-2), lost once (2-3)

### Best performing: v5_hybrid (adaptive)
- Phase-based strategy switching:
  - `desperate` (length -2+): 극공격 음식 수집
  - `balanced` (같음): 포도 우선 + 안전
  - `pressure` (length +1~2): 공격적 차단
  - `dominate` (length +3+): 가두기 + stalemate 유도

## How to Test

### Local self-play (봇 vs 봇):
```bash
# 터미널 1: 로컬 서버
cd ../copperhead-server
python3 main.py --settings ../tommy-bot/local_server_settings.json

# 터미널 2: 테스트
cd tommy-bot
python3 arena.py v3_trapper v5_hybrid --rounds 5
python3 arena.py --roundrobin --rounds 3
```

### Automated local tournament:
```bash
./tournament_local.sh v3_trapper v5_hybrid    # 1:1 대결
./tournament_local.sh --roundrobin 3          # 전체 라운드 로빈
```

### Online tournament (5개 봇 동시):
```bash
./tournament_online.sh
tail -f results/*.log           # 실시간 모니터링
```

### Single bot online:
```bash
python3 mybot.py --server wss://copperhead-server.politesmoke-80c82ad7.eastasia.azurecontainerapps.io/ws/
python3 run_bot.py v5_hybrid --server wss://... --name tommy_jhp
```

## Development Guidelines
- Python 3.9 호환 필수 (str | None 사용 금지 → Optional[str] 또는 타입 힌트 제거)
- f-string 대신 % 포맷 사용 권장 (호환성)
- calculate_move()는 250ms 이내 반환 필수 (틱 시간)
- 새 전략 추가: `strategies/v6_xxx.py`에 `Bot` 클래스 구현
- 테스트 후 최강 전략을 `mybot.py`에 통합

## Key Tactical Insights
1. **포도는 2배 가치**: +1 나, -1 상대 = 2점 스윙
2. **15x15는 좁다**: 벽 2칸 이내는 위험 구역
3. **꼬리는 다음 틱에 사라진다**: 자기 꼬리 뒤를 따라가면 안전
4. **상대 꼬리는 유지될 수 있다**: 상대가 먹으면 꼬리가 안 움직임
5. **정면충돌 시 길이가 같으면 마지막 방향전환자가 진다**: 직진 유지 시 유리
6. **30초 stalemate**: 더 길면 안 먹고 버티기가 승리 전략
7. **Flood fill 필수**: 막다른길 진입 = 즉사
