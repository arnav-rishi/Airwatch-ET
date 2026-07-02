"""
Vercel serverless entrypoint for the FastAPI backend.

Vercel's @vercel/python runtime looks for a module-level ASGI application named
`app` and serves it. The actual app and all its packages (routes/, services/,
utils/, prompts.py, data/) live one directory up, in the backend root, so we add
that directory to sys.path before importing.

Every incoming request is routed here by backend/vercel.json's rewrite, and the
FastAPI app matches on the original path (e.g. /api/aqi/live, /health).
"""
import os
import sys

# backend/ is the parent of this api/ directory — make its modules importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402  (re-exported so Vercel can detect the ASGI app)
