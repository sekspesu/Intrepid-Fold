from __future__ import annotations
"""
Solana Community Mood Tracker — Dashboard Server.
Flask-based web dashboard with trigger button & data visualization.
"""

import asyncio
import json
import logging
import os
import threading
from datetime import datetime
from typing import Any

from flask import Flask, jsonify, render_template, request

from src.config import DATA_DIR, DRY_RUN, PREDICTIONS_FILE
from src.history_tracker import get_accuracy_stats, _load_predictions

logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
)

# Store latest run data in memory
_latest_result = {
    "status": "idle",
    "last_run": None,
    "prediction": None,
    "data_summary": None,
    "error": None,
}
_run_lock = threading.Lock()


def _run_pipeline_async():
    """Run the pipeline in a background thread."""
    global _latest_result

    with _run_lock:
        if _latest_result["status"] == "running":
            return

        _latest_result["status"] = "running"
        _latest_result["error"] = None

    try:
        from src.main import run_pipeline

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        prediction = loop.run_until_complete(run_pipeline(dry_run=DRY_RUN))
        loop.close()

        _latest_result["status"] = "done"
        _latest_result["last_run"] = datetime.utcnow().isoformat()
        _latest_result["prediction"] = prediction

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        _latest_result["status"] = "error"
        _latest_result["error"] = str(e)


# ── Routes ──────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the dashboard."""
    return render_template("dashboard.html")


@app.route("/api/trigger", methods=["POST"])
def trigger_analysis():
    """Trigger a new analysis run."""
    if _latest_result["status"] == "running":
        return jsonify({"status": "already_running", "message": "Analysis is already in progress"})

    thread = threading.Thread(target=_run_pipeline_async, daemon=True)
    thread.start()

    return jsonify({"status": "started", "message": "Analysis pipeline started"})


@app.route("/api/status")
def get_status():
    """Get current pipeline status."""
    return jsonify({
        "status": _latest_result["status"],
        "last_run": _latest_result["last_run"],
        "error": _latest_result["error"],
    })


@app.route("/api/latest")
def get_latest():
    """Get the latest prediction result."""
    prediction = _latest_result.get("prediction")
    if not prediction:
        # Try to load the most recent from history
        predictions = _load_predictions()
        if predictions:
            prediction = predictions[-1]

    return jsonify({"prediction": prediction})


@app.route("/api/history")
def get_history():
    """Get prediction history."""
    predictions = _load_predictions()
    # Return most recent first, limit to 50
    predictions.reverse()
    return jsonify({"predictions": predictions[:50]})


@app.route("/api/accuracy")
def get_accuracy():
    """Get accuracy statistics."""
    stats = get_accuracy_stats()
    return jsonify(stats)


@app.route("/api/quick-data")
def get_quick_data():
    """Fetch quick market snapshot without running full pipeline."""
    import asyncio as aio

    async def _fetch_quick():
        from src.scrapers.price_scraper import scrape_price_data
        from src.scrapers.fear_greed_scraper import scrape_fear_greed

        price, fg = await aio.gather(
            scrape_price_data(),
            scrape_fear_greed(),
        )
        return {"price": price, "fear_greed": fg}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    data = loop.run_until_complete(_fetch_quick())
    loop.close()

    return jsonify(data)


def run_dashboard(host="0.0.0.0", port=5050, debug=False):
    """Start the dashboard server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger.info(f"🌐 Dashboard starting at http://localhost:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard(debug=True)
