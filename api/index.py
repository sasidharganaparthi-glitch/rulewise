"""Vercel Serverless Function entrypoint for RuleWise AI FastAPI application."""
import os
import sys

# Ensure root directory is added to sys.path so backend imports succeed
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.main import app  # noqa: E402, F401

