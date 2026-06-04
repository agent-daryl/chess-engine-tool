#!/usr/bin/env python3
"""
Chess Engine HTTP Server + Web Board

Neutral game manager with visual board at http://10.10.0.100:8081/board.html

Endpoints:
  GET  /state        — JSON: FEN, move list, turn, game status
  GET  /board.html   — Visual chess board (open in browser from laptop)
  POST /move         — { move: "e2e4", color: "white" }
  POST /move_san     — { move: "e4", color: "white" }
  POST /think        — triggers AI evaluator to play current side's best move
  POST /reset        — resets board
  GET  /health       — health check

Run:
  python3 tools/Chess_Engine/chess_server.py --port 8081
"""

import argparse
import json
import os
import sys
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock, Thread
import chess

DEFAULT_PORT = 8081
DEFAULT_HOST = "0.0.0.0"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

game_state = {
    "board": chess.Board(),
    "lock": Lock(),
    "move_history": [],
    "started": False,
}


def ascii_board(board: chess.Board) -> str:
    return board.unicode(borders=True)


BORDERS_HTML = os.path.join(SCRIPT_DIR, "board.html")


class ChessHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _cork(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cork()
        self.end_headers()

    def _send_json(self, data, code=200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self._cork()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/board.html" or self.path == "/":
            self._serve_html()

        elif self.path == "/state":
            with game_state["lock"]:
                b = game_state["board"]
                status = "in_progress"
                if b.is_checkmate():
                    status = "checkmate"
                elif b.is_stalemate():
                    status = "stalemate"
                elif b.is_insufficient_material():
                    status = "draw_insufficient"
                elif b.is_fivefold_repetition():
                    status = "draw_repetition"
                self._send_json({
                    "fen": b.fen(),
                    "board": ascii_board(b),
                    "turn": "white" if b.turn == chess.WHITE else "black",
                    "move_count": len(game_state["move_history"]),
                    "status": status,
                    "in_check": b.is_check(),
                    "legal_uci_moves": [m.uci() for m in b.legal_moves],
                    "legal_san_moves": [b.san(m) for m in b.legal_moves],
                    "move_history_san": [e["san"] for e in game_state["move_history"]],
                })

        elif self.path == "/reset":
            with game_state["lock"]:
                game_state["board"] = chess.Board()
                game_state["move_history"] = []
                game_state["started"] = False
            self._send_json({"ok": True, "message": "Board reset."})

        elif self.path == "/health":
            self._send_json({"ok": True, "version": "1.0"})

        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        # Routes that don't need a body
        if self.path == "/think":
            length_str = self.headers.get("Content-Length")
            if length_str is not None:
                length = int(length_str)
                raw = self.rfile.read(length)
            else:
                raw = b""
            payload = json.loads(raw) if raw else {}
            self._do_think(payload.get("depth", 4))
            return
        if self.path == "/reset":
            with game_state["lock"]:
                game_state["board"] = chess.Board()
                game_state["move_history"] = []
                game_state["started"] = False
            self._send_json({"ok": True, "message": "Board reset."})
            return

        # Robust body parsing for routes that need it
        length_str = self.headers.get("Content-Length")
        if length_str is not None:
            length = int(length_str)
            raw = self.rfile.read(length)
        else:
            raw = self.rfile.read()

        if not raw:
            self._send_json({"error": "invalid JSON or empty body"}, 400)
            return

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            self._send_json({
                "error": f"invalid JSON: {e}",
                "received": raw.decode('utf-8', errors='replace')
            }, 400)
            return

        if self.path == "/move":
            move_str = payload.get("move", "") or payload.get("uci", "")
            color_str = payload.get("color", "")
            if not move_str:
                self._send_json({"error": "move field required (UCI format)"}, 400)
                return
            self._apply_move(move_str, color_str, uci=True)

        elif self.path == "/move_san":
            move_san = payload.get("move", "") or payload.get("san", "")
            color_str = payload.get("color", "")
            if not move_san:
                self._send_json({"error": "move field required (SAN format)"}, 400)
                return
            self._apply_move(move_san, color_str, uci=False)

        elif self.path == "/think":
            self._do_think(payload.get("depth", 4))

        elif self.path == "/reset":
            with game_state["lock"]:
                game_state["board"] = chess.Board()
                game_state["move_history"] = []
                game_state["started"] = False
            self._send_json({"ok": True, "message": "Board reset."})

        else:
            self._send_json({"error": "not found"}, 404)

    def _apply_move(self, move_str, color_str, uci=True):
        with game_state["lock"]:
            b = game_state["board"]
            try:
                if uci:
                    parsed = chess.Move.from_uci(move_str)
                else:
                    parsed = b.parse_san(move_str)
            except (ValueError, chess.InvalidMoveError) as e:
                self._send_json({"error": f"invalid move: {e}",
                    "legal_moves": [m.uci() for m in b.legal_moves]}, 400)
                return
            if parsed not in b.legal_moves:
                self._send_json({"error": f"illegal move",
                    "legal_moves": [m.uci() for m in b.legal_moves]}, 409)
                return
            game_state["started"] = True
            san = b.san(parsed)
            game_state["move_history"].append({
                "uci": parsed.uci(),
                "san": san,
                "color": color_str or ("white" if b.turn == chess.WHITE else "black"),
            })
            b.push(parsed)
            self._send_json({
                "ok": True,
                "move": parsed.uci(),
                "san": san,
                "fen": b.fen(),
                "board": ascii_board(b),
                "in_check": b.is_check(),
                "is_checkmate": b.is_checkmate(),
                "is_stalemate": b.is_stalemate(),
                "move_count": len(game_state["move_history"]),
            })

    def _do_think(self, depth=4):
        """Run evaluator to find best move, apply it, return result."""
        with game_state["lock"]:
            b = game_state["board"]
            fen = b.fen()
            turn = "white" if b.turn == chess.WHITE else "black"
            if b.is_game_over():
                self._send_json({"error": "game over", "status": b.result()})
                return

        evaluator = os.path.join(SCRIPT_DIR, "chess_evaluator.py")
        result = subprocess.run(
            [sys.executable, evaluator, "--fen", fen, "--depth", str(depth), "--json"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            self._send_json({"error": f"evaluator failed: {result.stderr}"})
            return

        try:
            ev = json.loads(result.stdout)
        except json.JSONDecodeError:
            self._send_json({"error": "bad evaluator output"})
            return

        best_uci = ev.get("move")
        if not best_uci:
            self._send_json({"error": "no move from evaluator"})
            return

        self._apply_move(best_uci, turn, uci=True)

    def _serve_html(self):
        if os.path.exists(BORDERS_HTML):
            with open(BORDERS_HTML, "rb") as f:
                data = f.read()
            self.send_response(200)
            self._cork()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._send_json({"error": "board.html not found"}, 404)


def main():
    parser = argparse.ArgumentParser(description="Chess Engine HTTP Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", type=str, default=DEFAULT_HOST)
    args = parser.parse_args()
    server = HTTPServer((args.host, args.port), ChessHandler)
    print(f"Chess server listening on {args.host}:{args.port}")
    print(f"Web board: http://{args.host}:{args.port}/board.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
