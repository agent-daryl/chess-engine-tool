#!/usr/bin/env python3
"""
Chess Agent Interface

Connects the AI agent to the chess server + evaluator. Handles game state,
move submission, and board rendering for opencode chat interaction.

Usage:
  python3 tools/Chess_Engine/chess_agent.py --action start
  python3 tools/Chess_Engine/chess_agent.py --action my_move --move "d2d4" --color white
  python3 tools/Chess_Engine/chess_agent.py --action my_turn
  python3 tools/Chess_Engine/chess_agent.py --action status
  python3 tools/Chess_Engine/chess_agent.py --action board
  python3 tools/Chess_Engine/chess_agent.py --action reset
  python3 tools/Chess_Engine/chess_agent.py --action moves

Environment:
  CHESS_SERVER_URL  — override server URL (default http://10.10.0.100:8081)
"""

import argparse
import json
import os
import sys
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.error_recovery import retry

SERVER_URL = os.environ.get("CHESS_SERVER_URL", "http://10.10.0.100:8081")
EVALUATOR_PATH = os.path.join(os.path.dirname(__file__), "chess_evaluator.py")
SEARCH_DEPTH = 3


@retry(max_retries=3, base_delay=1, max_delay=5)
def _get(path: str) -> dict:
    r = httpx.get(f"{SERVER_URL}{path}", timeout=10)
    r.raise_for_status()
    return r.json()


@retry(max_retries=3, base_delay=1, max_delay=5)
def _post(path: str, body: dict) -> dict:
    r = httpx.post(f"{SERVER_URL}{path}", json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def action_health():
    try:
        state = _get("/health")
        print(f"Server OK: {state}")
        return True
    except Exception as e:
        print(f"Server unreachable: {e}")
        print("Start it with: python3 tools/Chess_Engine/chess_server.py &")
        return False


def action_start():
    ok = action_health()
    if not ok:
        return
    _do_reset()


def action_reset():
    _do_reset()


def _do_reset():
    _get("/reset")
    state = _get("/state")
    print("Board reset.")
    print(state.get("board", ""))


def action_status():
    try:
        state = _get("/state")
    except Exception as e:
        print(f"Error reaching server: {e}")
        return

    print(f"Status: {state['status']}")
    print(f"Turn: {state['turn']}")
    print(f"FEN: {state['fen']}")
    print(f"Move count: {state['move_count']}")
    if state.get("in_check"):
        print("CHECK!")


def action_board():
    try:
        state = _get("/state")
    except Exception as e:
        print(f"Error reaching server: {e}")
        return
    print(state.get("board", ""))
    print(f"FEN: {state['fen']}")


def action_moves():
    try:
        state = _get("/state")
    except Exception as e:
        print(f"Error reaching server: {e}")
        return

    legal = state.get("legal_san_moves", [])
    print(f"Legal moves ({len(legal)}): {', '.join(legal)}")


def action_my_move(move: str, color: str):
    """User submitted a move. Apply it, then print board."""
    try:
        import chess
        state = _get("/state")
        board = chess.Board(state["fen"])

        parsed = chess.Move.from_uci(move)
        if parsed not in board.legal_moves:
            legal = [m.uci() for m in board.legal_moves]
            print(f"ERROR: Illegal move '{move}'")
            print(f"Legal moves (UCI): {', '.join(legal)}")
            return

        result = _post("/move", {"move": move, "color": color})
        if "ok" in result:
            print(f"Move accepted: {result['san']} ({move})")
            print(result.get("board", ""))
            if result.get("is_checkmate"):
                print("CHECKMATE!")
            elif result.get("is_stalemate"):
                print("STALEMATE!")
            elif result.get("in_check"):
                print("Opponent is in check.")
        else:
            print(f"Error: {result.get('error', 'unknown')}")
    except Exception as e:
        print(f"Error: {e}")


def action_my_turn():
    """AI agent's turn to move. Evaluate position, pick best move, submit."""
    import subprocess

    try:
        state = _get("/state")
    except Exception as e:
        print(f"Error reaching server: {e}")
        return

    if state["status"] != "in_progress":
        print(f"Game is not in progress (status: {state['status']})")
        return

    fen = state["fen"]
    turn = state["turn"]

    result = subprocess.run(
        [sys.executable, EVALUATOR_PATH, "--fen", fen, "--depth", str(SEARCH_DEPTH), "--json"],
        capture_output=True, text=True, timeout=300,
    )

    if result.returncode != 0:
        print(f"Evaluator error: {result.stderr}")
        return

    try:
        eval_result = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Evaluator output not valid JSON: {result.stdout}")
        return

    if eval_result.get("move") is None:
        print(f"Game over: {eval_result.get('status', 'unknown')}")
        return

    best_move = eval_result["move"]
    best_san = eval_result["san"]
    best_score = eval_result["score"]
    assessment = eval_result["assessment"]

    move_result = _post("/move", {"move": best_move, "color": turn})

    if "ok" in move_result:
        print(f"\n--- My move ---")
        print(f"Move: {best_san} (UCI: {best_move})")
        print(f"Score: {best_score}")
        print(f"Assessment: {assessment}")
        print(f"\nBoard:")
        print(move_result.get("board", ""))
        print(f"FEN: {move_result['fen']}")
        if move_result.get("is_checkmate"):
            print("\nCHECKMATE — I won!")
        elif move_result.get("is_stalemate"):
            print("\nSTALEMATE — draw!")
        elif move_result.get("in_check"):
            print("\nOpponent is in check.")
    else:
        print(f"Move rejected: {move_result.get('error', 'unknown')}")


def main():
    parser = argparse.ArgumentParser(description="Chess Agent Interface")
    sub = parser.add_subparsers(dest="action", help="Action to perform")

    sub.add_parser("start", help="Start a new game (resets board)")
    sub.add_parser("reset", help="Reset the board")
    sub.add_parser("status", help="Show game status")
    sub.add_parser("board", help="Show current board")
    sub.add_parser("moves", help="Show legal moves")
    sub.add_parser("health", help="Check server health")

    m = sub.add_parser("my_move", help="Submit my (human) move")
    m.add_argument("--move", type=str, required=True, help="UCI move (e.g. e2e4)")
    m.add_argument("--color", type=str, required=True, help="white or black")

    sub.add_parser("my_turn", help="AI agent's turn — evaluate and play")
    sub.add_parser("play", help="Alias for my_turn")

    sub.add_parser("state", help="Raw server state (JSON)")

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        sys.exit(1)

    if args.action == "start":
        action_start()
    elif args.action == "reset":
        action_reset()
    elif args.action == "status":
        action_status()
    elif args.action == "board":
        action_board()
    elif args.action == "moves":
        action_moves()
    elif args.action == "health":
        action_health()
    elif args.action == "my_move":
        action_my_move(args.move, args.color)
    elif args.action in ("my_turn", "play"):
        action_my_turn()
    elif args.action == "state":
        print(json.dumps(_get("/state"), indent=2))


if __name__ == "__main__":
    main()
