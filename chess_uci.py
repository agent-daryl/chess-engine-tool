#!/usr/bin/env python3
"""
UCI Engine — Raw UCI protocol implementation for minimax evaluator.

Reads UCI commands from stdin, sends responses to stdout.

Usage:
  python3 tools/Chess_Engine/chess_uci.py --depth 3
"""

import argparse
import os
import sys
import time
import chess
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chess_evaluator import best_move


class UCIGame:
    """Simple UCI protocol handler."""

    def __init__(self, depth=3):
        self.board = chess.Board()
        self.depth = depth
        self.search_thread = None
        self.output_lock = threading.Lock()

    def _send(self, line):
        with self.output_lock:
            print(line, flush=True)

    def cmd_uci(self):
        self._send("id name QwenChess")
        self._send("id author Qwen AI Agent")
        self._send("uciok")

    def cmd_isready(self):
        self._send("readyok")

    def cmd_newgame(self):
        self.board = chess.Board()

    def cmd_position(self, tokens):
        if tokens[0] == "startpos":
            self.board = chess.Board()
            if "moves" in tokens:
                for mv in tokens[tokens.index("moves") + 1:]:
                    try:
                        m = chess.Move.from_uci(mv)
                        if m in self.board.legal_moves:
                            self.board.push(m)
                    except ValueError:
                        pass
        elif tokens[0] == "fen":
            fen_str = " ".join(tokens[1:7])
            self.board = chess.Board(fen_str)
            if "moves" in tokens:
                for mv in tokens[tokens.index("moves") + 1:]:
                    try:
                        m = chess.Move.from_uci(mv)
                        if m in self.board.legal_moves:
                            self.board.push(m)
                    except ValueError:
                        pass

    def cmd_go(self, tokens):
        if self.search_thread and self.search_thread.is_alive():
            self.search_thread.join(timeout=2)
        self.search_thread = threading.Thread(target=self._run_search, args=(tokens,), daemon=True)
        self.search_thread.start()

    def _run_search(self, tokens):
        search_depth = self.depth
        for i, tok in enumerate(tokens):
            if tok == "depth" and i + 1 < len(tokens):
                try:
                    search_depth = int(tokens[i + 1])
                except ValueError:
                    pass

        fen = self.board.fen()
        result = best_move(fen, depth=search_depth, max_workers=8)

        move = result.get("move")
        score = result.get("score", 0)

        if not move:
            self._send("info string game over")
            return

        mv = chess.Move.from_uci(move)
        san = self.board.san(mv)

        if self.board.turn == chess.BLACK:
            score = -score

        self._send(f"info depth {search_depth} score cp {score} pv {san}")
        self._send(f"bestmove {mv.uci()}")

    def cmd_stop(self):
        pass

    def cmd_quit(self):
        if self.search_thread and self.search_thread.is_alive():
            self.search_thread.join(timeout=5)
        raise SystemExit(0)

    def cmd_debug(self, tokens):
        pass

    def cmd_ucioption(self, tokens):
        for i, tok in enumerate(tokens):
            if tok.upper() == "NAME" and i + 1 < len(tokens):
                name = tokens[i + 1].lower()
                if name == "depth" and "VALUE" in tokens:
                    vi = tokens.index("VALUE")
                    if vi + 1 < len(tokens):
                        try:
                            self.depth = int(tokens[vi + 1])
                        except ValueError:
                            pass

    def cmd_register(self, tokens):
        pass

    def run(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            tokens = line.lower().split()
            cmd = tokens[0] if tokens else ""
            if cmd == "uci":
                self.cmd_uci()
            elif cmd == "isready":
                self.cmd_isready()
            elif cmd == "ucinewgame":
                self.cmd_newgame()
            elif cmd == "position":
                self.cmd_position(tokens[1:])
            elif cmd == "go":
                self.cmd_go(tokens[1:])
            elif cmd == "stop":
                self.cmd_stop()
            elif cmd == "quit":
                self.cmd_quit()
            elif cmd == "debug":
                self.cmd_debug(tokens[1:])
            elif cmd == "setoption":
                self.cmd_ucioption(tokens[1:])
            elif cmd == "register":
                self.cmd_register(tokens[1:])


def main():
    parser = argparse.ArgumentParser(description="UCI Chess Engine")
    parser.add_argument("--depth", type=int, default=3, help="Search depth (default 3)")
    args = parser.parse_args()
    UCIGame(depth=args.depth).run()


if __name__ == "__main__":
    main()
