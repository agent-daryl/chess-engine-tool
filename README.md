# Chess Engine Tool v0.9

Chess engine tool for the AI agent to play chess with the user via opencode chat interface.

**Version 0.9** — Functional release. Working minimax engine, visual web board, and HTTP game manager. Next release adds transposition tables, quiescence search, and neural net evaluator.

## Architecture

Five components:

| Script | Role |
|---|---|-
| `chess_server.py` | Neutral HTTP server — manages board state, validates moves, tracks game history |
| `chess_evaluator.py` | Minimax + alpha-beta pruning engine with piece-square tables. Parallel move evaluation |
| `chess_agent.py` | Agent CLI interface — connects server + evaluator for opencode chat game flow |
| `chess_uci.py` | UCI protocol wrapper for XBoard/chess GUI integration |
| `chess_uci_server.py` | TCP relay that exposes UCI engine over network for remote XBoard |

## How to Play

### Option 1: Chat interface (no GUI needed)

Start server and use the agent CLI:

```bash
# On RHEL host, start the chess server in background
python3 tools/Chess_Engine/chess_server.py --port 8081 &

# Tell me to start the game
python3 tools/Chess_Engine/chess_agent.py start

# Tell me to play
python3 tools/Chess_Engine/chess_agent.py my_turn

# Submit your move
python3 tools/Chess_Engine/chess_agent.py my_move --move e2e4 --color white
```

### Option 2: XBoard GUI (recommended — visual board)

**Step 1:** On RHEL host, start the UCI TCP server (in background):

```bash
python3 tools/Chess_Engine/chess_uci_server.py --port 5000 --depth 3 &
```

**Step 2:** On your laptop (Ubuntu), launch XBoard and point it at the UCI server:

```bash
xboard -fcp "tcp/10.10.0.100/5000 --proto xc"
```

XBoard handles the board, move entry, and game management. You click pieces, XBoard sends move to server, server queries minimax engine, engine responds through UCI protocol.

**Step 3:** Click New Game in XBoard and enjoy.

## Server Endpoints

| Method | Path | Payload | Returns |
|---|---|-−-|-−|
| GET | `/state` | — | FEN, board, turn, legal moves, game status |
| POST | `/move` | `{move: "e2e4", color: "white"}` | Accepted/rejected, new board, FEN |
| GET | `/reset` | — | Fresh board |
| GET | `/health` | — | Health check |

## Evaluator Details

- **Algorithm:** Minimax with alpha-beta pruning
- **Evaluation:** Piece values + piece-square tables (positional bonuses)
- **Parallelization:** Each legal move evaluated independently via ThreadPoolExecutor
- **Default depth:** 3 (adjustable, higher = better but slower)
- **Default workers:** 8 (uses CPU cores)

### Piece Values

| Piece | Value |
|---|---|
| Pawn | 100 |
| Knight | 320 |
| Bishop | 330 |
| Rook | 500 |
| Queen | 900 |
| King | 20000 |

## Dependencies

- `python-chess` (installed)
- `httpx` (pre-installed on RHEL host)

## Testing

```bash
python3 -m unittest Chess_Engine.tests.test_chess -v
```

6/7 tests passing (server health skips when server not running).

## Future Enhancements

- Increase search depth for better play
- Add transposition table caching
- Add quiescence search to avoid horizon effects
- Train neural net evaluator (Leela Chess Zero-style) using AI-box GPUs
- Client mode for connecting to remote servers
- PGN export and game analysis
