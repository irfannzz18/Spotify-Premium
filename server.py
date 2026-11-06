import os
import time
import threading
from collections import OrderedDict

import requests
import yt_dlp
from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

app = Flask(__name__, static_folder="web", static_url_path="")

# Small in-memory caches. They reset when the Render service restarts.
search_cache = OrderedDict()
stream_cache = {}
cache_lock = threading.Lock()

SEARCH_CACHE_SECONDS = 180
STREAM_CACHE_SECONDS = 240


def clean_text(value):
    return str(value or "").strip()


def get_ydl_options():
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "default_search": "ytsearch",
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 1,
    }


def search_youtube(query):
    query = clean_text(query)

    if not query:
        return []

    cache_key = query.lower()

    with cache_lock:
        cached = search_cache.get(cache_key)
        if cached and time.time() - cached["time"] < SEARCH_CACHE_SECONDS:
            search_cache.move_to_end(cache_key)
            return cached["results"]

    options = get_ydl_options()
    options["extract_flat"] = "in_playlist"

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            data = ydl.extract_info(
                "ytsearch15:" + query,
                download=False
            )

        entries = data.get("entries") or []
        results = []

        for item in entries:
            if not item:
                continue

            video_id = clean_text(item.get("id"))
            if not video_id:
                continue

            results.append({
                "id": video_id,
                "title": clean_text(item.get("title")) or "Unknown title",
                "artist": clean_text(
                    item.get("uploader")
                    or item.get("channel")
                    or item.get("artist")
                ) or "Unknown artist",
                "thumbnail": clean_text(item.get("thumbnail")),
                "duration": item.get("duration"),
                "url": "https://www.youtube.com/watch?v=" + video_id,
            })

        with cache_lock:
            search_cache[cache_key] = {
                "time": time.time(),
                "results": results,
            }
            search_cache.move_to_end(cache_key)

            while len(search_cache) > 60:
                search_cache.popitem(last=False)

        return results

    except Exception as exc:
        app.logger.exception("Search failed: %s", exc)
        return []


def resolve_audio(video_id):
    video_id = clean_text(video_id)

    if not video_id:
        raise ValueError("Missing song ID")

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
        "socket_timeout": 20,
        "retries": 2,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info or not info.get("url"):
        raise RuntimeError("Could not resolve audio")

    result = {
        "url": info["url"],
        "headers": info.get("http_headers") or {},
        "title": clean_text(info.get("title")),
    }

    with cache_lock:
        stream_cache[video_id] = {
            "time": time.time(),
            "info": result,
        }

    return result


@app.get("/")
def home():
    return send_from_directory("web", "index.html")


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "Snuffy Web",
    })


@app.get("/api/search")
def api_search():
    query = clean_text(request.args.get("q"))

    if not query:
        return jsonify({"results": []})

    results = search_youtube(query)
    return jsonify({"results": results})


@app.get("/api/stream/<video_id>")
def api_stream(video_id):
    try:
        info = resolve_audio(video_id)
        headers = dict(info.get("headers") or {})

        # Forward browser Range requests so seeking can work.
        range_header = request.headers.get("Range")
        if range_header:
            headers["Range"] = range_header

        upstream = requests.get(
            info["url"],
            headers=headers,
            stream=True,
            timeout=(15, 60),
            allow_redirects=True,
        )

        if upstream.status_code not in (200, 206):
            upstream.close()
            return jsonify({
                "error": "Audio provider returned an error",
                "status": upstream.status_code,
            }), 502

        response_headers = {}

        for key in (
            "Content-Type",
            "Content-Length",
            "Content-Range",
            "Accept-Ranges",
        ):
            value = upstream.headers.get(key)
            if value:
                response_headers[key] = value

        response_headers["Cache-Control"] = "no-store"

        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return Response(
            stream_with_context(generate()),
            status=upstream.status_code,
            headers=response_headers,
            content_type=upstream.headers.get(
                "Content-Type",
                "audio/webm"
            ),
        )

    except Exception as exc:
        app.logger.exception("Audio stream failed: %s", exc)
        return jsonify({
            "error": "Unable to start audio. Try another song."
        }), 502


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory("web", "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
