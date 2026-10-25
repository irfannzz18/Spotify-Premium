import json
from yt_dlp import YoutubeDL

BASE = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extractor_args": {"youtube": {"player_client": ["ios", "android"]}},
}


def search(query, count=10):
    opts = dict(BASE, extract_flat=True)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{count}:{query}", download=False)
    out = []
    for e in (info or {}).get("entries") or []:
        if not e or not e.get("id"):
            continue
        vid = e["id"]
        out.append({
            "id": vid,
            "title": e.get("title") or "Unknown",
            "artist": e.get("uploader") or e.get("channel") or "YouTube",
            "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
        })
    return json.dumps(out)


def stream_url(target):
    opts = dict(BASE, format="bestaudio[ext=m4a]/bestaudio/best")
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=False)
        if "entries" in info:
            info = next(e for e in info["entries"] if e)
    return json.dumps({
        "url": info["url"],
        "headers": info.get("http_headers") or {},
    })
