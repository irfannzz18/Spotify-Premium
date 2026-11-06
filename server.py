
import os
from flask import Flask, jsonify, request, send_from_directory
from yt_dlp import YoutubeDL

app = Flask(__name__)

YDL_BASE = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android"]
        }
    },
}


@app.get("/")
def home():
    return send_from_directory("web", "index.html")


@app.get("/health")
def health():
    return jsonify(
        status="ok",
        app="Snuffy Web"
    )


@app.get("/api/search")
def search():
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify(results=[])

    if len(query) > 180:
        return jsonify(error="Search query is too long"), 400

    try:
        opts = dict(YDL_BASE, extract_flat=True)

        with YoutubeDL(opts) as ydl:
            data = ydl.extract_info(
                "ytsearch15:" + query,
                download=False
            )

        results = []

        for item in (data or {}).get("entries") or []:
            if not item or not item.get("id"):
                continue

            video_id = item["id"]

            results.append({
                "id": video_id,
                "title": item.get("title") or "Unknown title",
                "artist": (
                    item.get("uploader")
                    or item.get("channel")
                    or "YouTube"
                ),
                "thumb": (
                    "https://i.ytimg.com/vi/"
                    + video_id
                    + "/mqdefault.jpg"
                )
            })

        return jsonify(results=results)

    except Exception:
        app.logger.exception("YouTube search failed")

        return jsonify(
            error="Music search is temporarily unavailable. Please try again."
        ), 502


@app.get("/api/resolve")
def resolve():
    video_id = request.args.get("id", "").strip()

    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_"
    )

    if (
        not video_id
        or len(video_id) > 40
        or any(c not in allowed for c in video_id)
    ):
        return jsonify(error="Invalid track ID"), 400

    try:
        opts = dict(
            YDL_BASE,
            format="bestaudio[ext=m4a]/bestaudio/best"
        )

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                "https://www.youtube.com/watch?v=" + video_id,
                download=False
            )

        if not info or not info.get("url"):
            raise RuntimeError("No audio stream was returned")

        return jsonify(url=info["url"])

    except Exception:
        app.logger.exception("Audio resolution failed")

        return jsonify(
            error="This track could not be played right now. Try another result."
        ), 502


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
    )
  
