#!/usr/bin/env python3
"""
Chess Move Evaluator — Minimax with Alpha-Beta Pruning + Piece-Square Tables

Inputs a FEN string, outputs the best move with evaluation score and
human-readable assessment.

Parallel search using concurrent.futures across CPU cores.

Usage from the AI agent or CLI:
  python3 tools/Chess_Engine/chess_evaluator.py --fen "rnbqkbnr/pppppppp/8/8/4P3/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1" --depth 3
  python3 tools/Chess_Engine/chess_evaluator.py --fen "rnbqkbnr/pppppppp/8/8/4P3/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1" --depth 3 --json
"""

import argparse
import sys
import chess
from multiprocessing import Pool, cpu_count
from dataclasses import dataclass
from typing import List, Tuple, Optional

MAX_WORKERS = cpu_count()  # Uses all available cores (40 on RHEL host)


# ── Piece-square tables (from Classic Chess Engine, inverted for black) ──

pawn_table = [
    0,   0,   0,   0,   0,   0,   0,   0,
    50,  50,  50,  50,  50,  50,  50,  50,
    10,  10,  20,  30,  30,  20,  10,  10,
    5,   5,  10,  25,  25,  10,   5,   5,
    0,   0,   0,  20,  20,   0,   0,   0,
    5, -5, -10,   0,   0, -10,  -5,   5,
    5,  10,  20, -30, -30,  20,  10,   5,
    0,   0,   0,   0,   0,   0,   0,   0,
]

knight_table = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20,   0,   0,   0,   0, -20, -40,
    -30,   0,  10,  15,  15,  10,   0, -30,
    -30,   5,  15,  20,  20,  15,   5, -30,
    -30,   0,  15,  20,  20,  15,   0, -30,
    -30,   5,  10,  15,  15,  10,   5, -30,
    -40, -20,   0,   5,   5,   0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]

bishop_table_start = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,  10,  10,  10,  10,   0, -10,
    -10,   5,   5,  10,  10,   5,   5, -10,
    -10,   0,   5,  10,  10,   5,   0, -10,
    -10,  10,  10,  10,  10,  10,  10, -10,
    -10,   5,   0,   0,   0,   0,   5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
]

rook_table = [
    0,   0,   0,   0,   0,   0,   0,   0,
    5,  10,  10,  10,  10,  10,  10,   5,
   -5,   0,   0,   0,   0,   0,   0,  -5,
   -5,   0,   0,   0,   0,   0,   0,  -5,
   -5,   0,   0,   0,   0,   0,   0,  -5,
   -5,   0,   0,   0,   0,   0,   0,  -5,
   -5,   0,   0,   0,   0,   0,   0,  -5,
    0,   0,   0,   5,   5,   0,   0,   0,
]

queen_table = [
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,   5,   5,   5,   0, -10,
     -5,   0,   5,   5,   5,   5,   0,  -5,
      0,   0,   5,   5,   5,   5,   0,   -5,
    -10,   5,   5,   5,   5,   5,   0, -10,
    -10,   0,   5,   0,   0,   0,   0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
]

king_table_start = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
     20,  20,  0,   0,   0,   0,  20,  20,
     20,  30,  10,   0,   0,  10,  30,  20,
]


piece_values = {
    chess.PAWN:   100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK:   500,
    chess.QUEEN:  900,
    chess.KING:  20000,
}

pst_map = {
    (chess.PAWN, chess.WHITE): pawn_table,
    (chess.KNIGHT, chess.WHITE): knight_table,
    (chess.BISHOP, chess.WHITE): bishop_table_start,
    (chess.ROOK, chess.WHITE): rook_table,
    (chess.QUEEN, chess.WHITE): queen_table,
    (chess.KING, chess.WHITE): king_table_start,
}


def evaluate_board(board: chess.Board) -> int:
    """Evaluate position from active player's perspective."""
    score = 0
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None:
            continue

        piece_type = piece.piece_type
        color = piece.color

        base_value = piece_values.get(piece_type, 0)
        if not base_value:
            continue

        pst_key = (piece_type, color)
        if color == chess.WHITE:
            score += base_value

            if pst_key in pst_map:
                idx = sq
                score += pst_map[pst_key][idx]
        else:
            score -= base_value

            if pst_key in pst_map:
                idx = 56 + 7 - (sq % 8) + (sq // 8) * 8
                idx = 56 + 7 - (sq % 8) + (sq // 8) * 8
                flipped = 56 - (sq % 8) + (112 - sq)
                flipped_sq = 56 - (sq % 8) + (sq // 8) * 8
                flipped_sq = 63 - sq
                score -= pst_map[pst_key][flipped_sq]

    return score


def minimax_node(board: chess.Board, depth: int, alpha: int, beta: int, maximizing: bool):
    """Recursive minimax with alpha-beta pruning."""
    if depth == 0 or board.is_game_over():
        return evaluate_board(board)

    moves = list(board.legal_moves)
    if not moves:
        if board.is_checkmate():
            return -20000 if maximizing else 20000
        return 0

    if maximizing:
        best = float('-inf')
        for move in moves:
            board.push(move)
            val = minimax_node(board, depth - 1, alpha, beta, False)
            board.pop()
            best = max(best, val)
            alpha = max(alpha, val)
            if beta <= alpha:
                break
        return best
    else:
        best = float('inf')
        for move in moves:
            board.push(move)
            val = minimax_node(board, depth - 1, alpha, beta, True)
            board.pop()
            best = min(best, val)
            beta = min(beta, val)
            if beta <= alpha:
                break
        return best


def evaluate_move_worker(args):
    """Worker function for multiprocessing. Receives (fen, uci_move, depth)."""
    board = chess.Board(args[0])
    move = chess.Move.from_uci(args[1])
    depth = args[2]
    board.push(move)
    val = minimax_node(board, depth - 1, float('-inf'), float('inf'), board.turn == chess.WHITE)
    board.pop()
    return move.uci(), val


def best_move(fen: str, depth: int = 3, max_workers: int = MAX_WORKERS) -> dict:
    """Find best move for current position. Returns dict with move, score, assessment."""
    board = chess.Board(fen)

    if board.is_game_over():
        return {
            "move": None,
            "san": None,
            "score": 0,
            "status": board.result(),
            "assessment": "Game over.",
        }

    moves = list(board.legal_moves)
    move_values = []

    # Prepare args for multiprocessing workers (FEN string + UCI move + depth)
    worker_args = [(fen, move.uci(), depth) for move in moves]

    with Pool(processes=max_workers) as pool:
        for uci, val in pool.imap_unordered(evaluate_move_worker, worker_args):
            move_values.append((chess.Move.from_uci(uci), val))

    turn = board.turn
    if turn == chess.WHITE:
        best = max(move_values, key=lambda x: x[1])
    else:
        best = min(move_values, key=lambda x: x[1])

    best_move_obj, best_score = best
    san = board.san(best_move_obj)
    uci = best_move_obj.uci()

    if turn == chess.BLACK:
        best_score = -best_score

    assessment = score_to_assessment(best_score, board)

    return {
        "move": uci,
        "san": san,
        "score": best_score,
        "depth": depth,
        "move_count_evaluated": len(move_values),
        "assessment": assessment,
        "fen_after": board.fen(),
    }


def score_to_assessment(score: int, board: chess.Board) -> str:
    """Convert numeric score to human confidence level."""
    abs_score = abs(score)

    if board.is_check():
        check_note = " Opponent is in check."
    else:
        check_note = ""

    if abs_score > 2000:
        level = "This is a dominant position. Winning is highly likely."
    elif abs_score > 1000:
        level = "Strong advantage. Probable win if I don't blunder."
    elif abs_score > 500:
        level = "Solid advantage. Good chances to convert."
    elif abs_score > 200:
        level = "Slight edge. Worth pursuing."
    elif abs_score > 50:
        level = "Marginally better. Even game, slight tilt."
    else:
        level = "Nearly equal. Careful play needed from both sides."

    if board.is_checkmate():
        level = "Checkmate!"
    elif board.is_stalemate():
        level = "Stalemate — draw."

    return f"{level}{check_note}"


def main():
    parser = argparse.ArgumentParser(description="Chess Move Evaluator (minimax + alpha-beta)")
    parser.add_argument("--fen", type=str, required=True, help="FEN string of current position")
    parser.add_argument("--depth", type=int, default=3, help="Search depth (default 3)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"Parallel workers (default {MAX_WORKERS})")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        ch = chess.Board(args.fen)
    except Exception as e:
        print(f"ERROR: Invalid FEN: {e}", file=sys.stderr)
        sys.exit(1)

    result = best_move(args.fen, depth=args.depth, max_workers=args.workers)

    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        print(f"FEN: {args.fen}")
        print(f"Board:\n{ch.unicode(borders=True)}")
        print(f"Turn: {'White' if ch.turn == chess.WHITE else 'Black'}")
        print(f"Best move: {result['san']} (UCI: {result['move']})")
        print(f"Score: {result['score']}")
        print(f"Depth: {result['depth']}")
        print(f"Moves evaluated: {result['move_count_evaluated']}")
        print(f"Assessment: {result['assessment']}")


if __name__ == "__main__":
    main()
