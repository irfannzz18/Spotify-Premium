import os
import time
import threading
from collections import OrderedDict

import requests
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="web", static_url_path="")

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
CACHE_SECONDS = 180
CACHE_LIMIT = 60

cache = OrderedDict()
cache_lock = threading.Lock()


def youtube_search(query):
    query = str(query or "").strip()

    if not query:
        return []

    if not API_KEY:
        raise RuntimeError(
            "YouTube API key is missing. "
            "Set YOUTUBE_API_KEY in Render environment variables."
        )

    cache_key = query.casefold()

    with cache_lock:
        saved = cache.get(cache_key)

        if saved and time.time() - saved["time"] < CACHE_SECONDS:
            cache.move_to_end(cache_key)
            return saved["results"]

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "type": "video",
            "videoCategoryId": "10",
            "maxResults": 15,
            "q": query,
            "key": API_KEY,
        },
        timeout=15,
    )

    if response.status_code != 200:
        try:
            message = response.json()["error"]["message"]
        except Exception:
            message = "YouTube API search failed"

        raise RuntimeError(message)

    payload = response.json()
    results = []

    for item in payload.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")

        if not video_id:
            continue

        snippet = item.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})

        thumbnail = (
            thumbnails.get("high")
            or thumbnails.get("medium")
            or thumbnails.get("default")
            or {}
        ).get("url", "")

        results.append({
            "id": video_id,
            "title": snippet.get("title") or "Unknown title",
            "artist": snippet.get("channelTitle") or "YouTube",
            "thumb": thumbnail or (
                f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            ),
        })

    with cache_lock:
        cache[cache_key] = {
            "time": time.time(),
            "results": results,
        }

        cache.move_to_end(cache_key)

        while len(cache) > CACHE_LIMIT:
            cache.popitem(last=False)

    return results


@app.get("/")
def home():
    return send_from_directory("web", "index.html")


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "Snuffy Web",
        "youtube_search_configured": bool(API_KEY),
    })


@app.get("/api/search")
def search():
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"results": []})

    try:
        return jsonify({"results": youtube_search(query)})

    except Exception as exc:
        app.logger.exception("YouTube API search error")

        return jsonify({
            "error": str(exc),
            "results": [],
        }), 502


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found"}), 404

    return send_from_directory("web", "index.html")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
