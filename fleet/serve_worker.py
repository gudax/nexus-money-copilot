#!/usr/bin/env python3
"""Serve one fleet worker over the A2A protocol: `serve_worker.py markets 8101`."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

import workers

if __name__ == "__main__":
    name, port = sys.argv[1], int(sys.argv[2])
    agent = getattr(workers, name)
    app = to_a2a(agent, port=port)  # serves /.well-known/agent-card.json
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
