import os
import re
import time
import threading
from collections import OrderedDict

import requests
import yt_dlp

from flask import Flask, Response, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="web", static_url_path="")

search_cache = OrderedDict()
stream_cache = {}
cache_lock = threading.Lock()

SEARCH_CACHE_SECONDS = 180
STREAM_CACHE_SECONDS = 180


def clean(value):
    return str(value or "").strip()


def valid_video_id(value):
    value = clean(value)
    return value if re.fullmatch(r"[A-Za-z0-9_-]{11}", value) else ""


def search_youtube(query):
    query = clean(query)
    if not query:
        return []

    key = query.lower()

    with cache_lock:
        cached = search_cache.get(key)
        if cached and time.time() - cached["time"] < SEARCH_CACHE_SECONDS:
            search_cache.move_to_end(key)
            return cached["results"]

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 2,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            data = ydl.extract_info(
                "ytsearch15:" + query,
                download=False
            )

        results = []

        for item in data.get("entries") or []:
            if not item:
                continue

            video_id = valid_video_id(item.get("id"))
            if not video_id:
                continue

            results.append({
                "id": video_id,
                "title": clean(item.get("title")) or "Unknown title",
                "artist": clean(
                    item.get("uploader")
                    or item.get("channel")
                    or item.get("artist")
                ) or "Unknown artist",
                "thumb": clean(item.get("thumbnail")),
                "duration": item.get("duration") or 0
            })

        with cache_lock:
            search_cache[key] = {
                "time": time.time(),
                "results": results
            }
            search_cache.move_to_end(key)

            while len(search_cache) > 50:
                search_cache.popitem(last=False)

        return results

    except Exception:
        app.logger.exception("YouTube search failed")
        return []


def resolve_audio(video_id):
    video_id = valid_video_id(video_id)

    if not video_id:
        raise ValueError("Invalid video ID")

    with cache_lock:
        cached = stream_cache.get(video_id)
        if cached and time.time() - cached["time"] < STREAM_CACHE_SECONDS:
            return cached["info"]

    url = "https://www.youtube.com/watch?v=" + video_id

    options = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "noplaylist": True,
        "socket_timeout": 25,
        "retries": 2,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info or not info.get("url"):
        raise RuntimeError("Audio URL unavailable")

    result = {
        "url": info["url"],
        "headers": info.get("http_headers") or {},
        "title": clean(info.get("title"))
    }

    with cache_lock:
        stream_cache[video_id] = {
            "time": time.time(),
            "info": result
        }

    return result


@app.get("/")
def home():
    return send_from_directory("web", "index.html")


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "Snuffy Web"
    })


@app.get("/api/search")
def api_search():
    query = clean(request.args.get("q"))

    if not query:
        return jsonify({"results": []})

    return jsonify({
        "results": search_youtube(query)
    })


@app.get("/api/stream/<video_id>")
def api_stream(video_id):
    upstream = None

    try:
        info = resolve_audio(video_id)
        headers = dict(info.get("headers") or {})

        range_header = request.headers.get("Range")
        if range_header:
            headers["Range"] = range_header

        upstream = requests.get(
            info["url"],
            headers=headers,
            stream=True,
            timeout=(20, 90),
            allow_redirects=True
        )

        if upstream.status_code not in (200, 206):
            status = upstream.status_code
            upstream.close()
            return jsonify({
                "error": "Audio source returned an error",
                "status": status
            }), 502

        response_headers = {}

        for name in (
            "Content-Type",
            "Content-Length",
            "Content-Range",
            "Accept-Ranges"
        ):
            value = upstream.headers.get(name)
            if value:
                response_headers[name] = value

        response_headers["Cache-Control"] = "no-store"

        def stream():
            try:
                for chunk in upstream.iter_content(64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return Response(
            stream(),
            status=upstream.status_code,
            headers=response_headers,
            content_type=upstream.headers.get(
                "Content-Type",
                "audio/webm"
            )
        )

    except Exception:
        if upstream:
            upstream.close()

        app.logger.exception("Audio streaming failed")
        return jsonify({
            "error": "Unable to play this song. Try another result."
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
        debug=False
    )
