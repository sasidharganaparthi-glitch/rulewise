"""Vercel Serverless Function entry point for RuleWise AI."""

import os
import sys

# Ensure project root is in the Python search path for Vercel Serverless runtime
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.main import app

# Export app as required by Vercel ASGI adapter
app = app
