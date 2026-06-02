#!/usr/bin/env python3
"""Tests for Chess Engine evaluator."""

import json
import os
import sys
import unittest
import subprocess

EVALUATOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chess_evaluator.py")
STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"


class TestEvaluator(unittest.TestCase):

    def test_evaluator_running_position(self):
        """Evaluator returns JSON with a valid move on a standard opening position."""
        r = subprocess.run(
            [sys.executable, EVALUATOR, "--fen", E4_FEN, "--depth", "3", "--json"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        result = json.loads(r.stdout)
        self.assertIn("move", result)
        self.assertIn("san", result)
        self.assertIn("score", result)
        self.assertIsNotNone(result["move"])
        self.assertIsNotNone(result["san"])

    def test_starting_position_legal_move(self):
        """Starting position should return a legal first move."""
        r = subprocess.run(
            [sys.executable, EVALUATOR, "--fen", STARTING_FEN, "--depth", "2", "--json"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        result = json.loads(r.stdout)
        self.assertIsNotNone(result["move"])
        self.assertIn(result["move"], [
            "e2e4", "e2e3", "d2d4", "d2d3",
            "g1f3", "b1c3", "g1h3", "b1a3"
        ])

    def test_invalid_fen_exits(self):
        """Invalid FEN should cause non-zero exit."""
        r = subprocess.run(
            [sys.executable, EVALUATOR, "--fen", "not_a_fen", "--depth", "2", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(r.returncode, 0)

    def test_json_output_valid(self):
        """Output should be valid JSON."""
        r = subprocess.run(
            [sys.executable, EVALUATOR, "--fen", E4_FEN, "--depth", "2", "--json"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        parsed = json.loads(r.stdout)
        self.assertIsInstance(parsed, dict)

    def test_depth_flag(self):
        """Depth 2 should be faster than depth 3 but both work."""
        for d in ("2", "3"):
            r = subprocess.run(
                [sys.executable, EVALUATOR, "--fen", E4_FEN, "--depth", d, "--json"],
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(r.returncode, 0, msg=r.stderr)

    def test_assessment_present(self):
        """Assessment field should be a non-empty string."""
        r = subprocess.run(
            [sys.executable, EVALUATOR, "--fen", E4_FEN, "--depth", "3", "--json"],
            capture_output=True, text=True, timeout=120,
        )
        parsed = json.loads(r.stdout)
        self.assertIn("assessment", parsed)
        self.assertTrue(len(parsed["assessment"]) > 0)


class TestServerEndpoints(unittest.TestCase):

    def test_server_health(self):
        """Server /health should return 200 with ok=True (skip if server not running)."""
        try:
            import httpx
            r = httpx.get("http://10.10.0.100:8081/health", timeout=3)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json()["ok"])
        except (httpx.RequestError, httpx.ConnectError):
            self.skipTest("Chess server not running")


if __name__ == "__main__":
    unittest.main()
