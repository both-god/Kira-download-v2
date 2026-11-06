import asyncio
import glob
import json
import logging
import os
import re
import shutil
import time
from urllib.parse import urlparse

import aiohttp
import yt_dlp

import config
import db

log = logging.getLogger("dl")


def _walk(o, k, out):
    if isinstance(o, dict):
        for kk, v in o.items():
            _walk(v, kk, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, k, out)
    elif isinstance(o, str) and o.startswith("http"):
        out.append((k.lower(), o))


def find_media_url(data, kind):
    flat = []
    _walk(data, "", flat)
    prefs = (["audio_url", "audio", "download_url", "stream_url", "url", "link"] if kind == "audio"
             else ["video_url", "video", "download_url", "stream_url", "url", "link"])
    for p in prefs:
        for k, v in flat:
            if k == p:
                return v
    return None


def find_title(data):
    if isinstance(data, dict):
        if isinstance(data.get("title"), str):
            return data["title"]
        for v in data.values():
            t = find_title(v)
            if t:
                return t
    elif isinstance(data, list):
        for v in data:
            t = find_title(v)
            if t:
                return t
    return None


async def _to_mp3(src, dst):
    p = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", src, "-vn", "-acodec", "libmp3lame", "-b:a", "192k", dst,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    if await p.wait() != 0 or not os.path.exists(dst):
        raise RuntimeError("ffmpeg convert mp3 បរាជ័យ")


_URL_KEYS = ("url", "stream_url", "download_url", "direct_url", "link", "src", "video_url", "audio_url")


def _collect(o, out):
    if isinstance(o, dict):
        if any(isinstance(o.get(k), str) and o[k].startswith("http") for k in _URL_KEYS):
            out.append(o)
        for v in o.values():
            _collect(v, out)
    elif isinstance(o, list):
        for v in o:
            _collect(v, out)


def pick_url(data, kind):
    """រើសតំណ media ល្អបំផុតពី JSON (គាំទ្រទម្រង់ផ្សេងៗ)"""
    cands = []
    _collect(data, cands)
    best, best_score = None, -1e9
    for d in cands:
        url = next(d[k] for k in _URL_KEYS if isinstance(d.get(k), str) and d[k].startswith("http"))
        text = " ".join(str(v).lower() for v in d.values() if not isinstance(v, (dict, list)) and not str(v).startswith("http"))
        keys = " ".join(d.keys()).lower()
        sc = 0.0
        if kind == "audio":
            sc += 5 if ("audio" in text or "audio" in keys) and "video" not in text else 0
            sc += 1 if "audio" in text else 0
        else:
            sc += 3 if "video" in text or "video" in keys else 0
            sc += 2 if "mp4" in text else 0
            sc += 2 if ("audio" in keys or "hasaudio" in keys or "audio" in text) and "video" in text else 0
            try:
                h = int(d.get("height") or 0)
                sc += min(h, 1080) / 1000 if h else 0
            except Exception:
                pass
        if sc > best_score:
            best, best_score = url, sc
    return best


PARTS = int(os.getenv("DL_PARTS", "8"))              # parallel connections
BLOCK = 4 * 1024 * 1024                              # size of each ranged block
MP3_BITRATE = os.getenv("MP3_BITRATE", "128k")       # lower = faster convert + smaller upload
HAS_FFMPEG = bool(shutil.which("ffmpeg"))
_BAD_HOSTS = ("youtube.com", "youtu.be", "tiktok.com", "facebook.com", "instagram.com")
_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
_LINK_KEYS = ("stream_url", "download_url", "audio_url", "video_url", "direct_url", "media_url", "src", "link")


def _is_text(ct):
    ct = (ct or "").lower()
    return ct.startswith("text/") or "json" in ct


def sniff(path):
    """Detect the real file format from magic bytes."""
    with open(path, "rb") as f:
        h = f.read(64)
    if h[4:8] == b"ftyp":
        return "mp4"
    if h[:3] == b"ID3" or (len(h) > 1 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0):
        return "mp3"
    if h[:4] == b"\x1aE\xdf\xa3":
        return "webm"
    if h[:4] == b"OggS":
        return "ogg"
    if h[:4] == b"fLaC":
        return "flac"
    if h[:4] == b"RIFF":
        return "riff"
    if h.lstrip()[:1] in (b"{", b"<", b"["):
        return "text"
    return "unknown"


def pick_link(data, source_url):
    """Find the real media link in the NUB JSON ('stream_url'), never the original page URL."""
    flat = []
    _walk(data, "", flat)
    good = []
    for k, v in flat:
        low = v.lower().split("?")[0]
        if v.rstrip(">)]}.,\"'") == source_url.rstrip(">)]}.,\"'") or low.endswith(_IMG_EXT):
            continue
        if any(h in v.lower() for h in _BAD_HOSTS):
            continue
        good.append((k, v))
    for gk in _LINK_KEYS:
        for k, v in good:
            if k == gk:
                return v
    return good[0][1] if good else None


def find_thumb(data):
    if isinstance(data, dict):
        for k in ("thumbnail", "thumb", "cover", "image"):
            v = data.get(k)
            if isinstance(v, list) and v:
                v = v[-1].get("url") if isinstance(v[-1], dict) else v[-1]
            if isinstance(v, dict):
                v = v.get("url")
            if isinstance(v, str) and v.startswith("http"):
                return v
        for v in data.values():
            t = find_thumb(v)
            if t:
                return t
    elif isinstance(data, list):
        for v in data:
            t = find_thumb(v)
            if t:
                return t
    return None


async def _save(r, jobdir, progress):
    """Stream one response to disk (single connection)."""
    path = os.path.join(jobdir, "raw.bin")
    total = int(r.headers.get("Content-Length", 0) or 0)
    if total > config.MAX_FILE:
        raise RuntimeError("ឯកសារធំជាង 2GB")
    done, last = 0, 0.0
    with open(path, "wb") as f:
        async for chunk in r.content.iter_chunked(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if done > config.MAX_FILE:
                raise RuntimeError("ឯកសារធំជាង 2GB")
            if progress and time.time() - last > 4:
                last = time.time()
                await progress(done, total)
    return path


async def _parallel(s, url, hdr, total, jobdir, progress):
    """Download with several ranged connections at once."""
    path = os.path.join(jobdir, "raw.bin")
    with open(path, "wb") as f:
        f.truncate(total)
    fh = open(path, "r+b")
    sem = asyncio.Semaphore(PARTS)
    state = {"done": 0, "last": 0.0}

    async def block(start, end):
        async with sem:
            for attempt in range(3):
                try:
                    async with s.get(url, headers={**hdr, "Range": f"bytes={start}-{end}"}) as r:
                        if r.status != 206:
                            raise RuntimeError(f"range HTTP {r.status}")
                        data = await r.read()
                    if len(data) != end - start + 1:
                        raise RuntimeError("block size mismatch")
                    fh.seek(start)
                    fh.write(data)
                    state["done"] += len(data)
                    if progress and time.time() - state["last"] > 4:
                        state["last"] = time.time()
                        await progress(state["done"], total)
                    return
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5)

    try:
        await asyncio.gather(*[block(i, min(i + BLOCK, total) - 1) for i in range(0, total, BLOCK)])
    finally:
        fh.close()
    return path


async def _fetch_media(s, link, headers, base, jobdir, progress):
    """Follow link(s) until real media arrives. Returns (kind, payload): ('file', path) or ('text', body)."""
    host = urlparse(base).netloc
    hdr = headers if urlparse(link).netloc == host else {}
    async with s.get(link, headers={**hdr, "Range": "bytes=0-0"}, allow_redirects=True) as r:
        ct = r.headers.get("Content-Type", "")
        if r.status not in (200, 206):
            raise RuntimeError(f"media HTTP {r.status}")
        if _is_text(ct):
            return "text", await r.text()
        final = str(r.url)
        cr = r.headers.get("Content-Range", "")
        total = int(cr.rsplit("/", 1)[1]) if r.status == 206 and "/" in cr and cr.rsplit("/", 1)[1].isdigit() else 0
        if r.status == 200:  # server ignored Range -> this response is the whole file
            return "file", await _save(r, jobdir, progress)
    if total > config.MAX_FILE:
        raise RuntimeError("ឯកសារធំជាង 2GB")
    fhdr = headers if urlparse(final).netloc == host else {}
    if total > 2 * BLOCK:
        try:
            return "file", await _parallel(s, final, fhdr, total, jobdir, progress)
        except Exception as e:
            log.warning("parallel download failed → single stream: %s", e)
    async with s.get(final, headers=fhdr, allow_redirects=True) as r2:
        if r2.status != 200:
            raise RuntimeError(f"media HTTP {r2.status}")
        return "file", await _save(r2, jobdir, progress)


async def _run(*args):
    p = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await p.communicate()
    return p.returncode, out, err


async def _normalize(src, kind, fmt, jobdir):
    """Make a valid, seekable mp4 / mp3 that Telegram can play."""
    if not HAS_FFMPEG:
        if (kind == "audio" and fmt == "mp3") or (kind != "audio" and fmt == "mp4"):
            return src
        raise RuntimeError(f"ឯកសារជាទម្រង់ '{fmt}' ប៉ុន្តែមិនមាន ffmpeg")
    if kind == "audio":
        if fmt == "mp3":
            return src
        out = os.path.join(jobdir, "audio.mp3")
        rc, _, err = await _run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-c:a", "libmp3lame",
                                "-b:a", MP3_BITRATE, "-threads", "0", out)
        if rc != 0 or not os.path.exists(out):
            raise RuntimeError("ffmpeg convert mp3 បរាជ័យ: " + err.decode("utf-8", "ignore")[:150])
        return out
    out = os.path.join(jobdir, "video.mp4")
    rc, _, _ = await _run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-c", "copy", "-movflags", "+faststart", out)
    if rc == 0 and os.path.exists(out):
        return out
    rc, _, err = await _run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-c:v", "libx264", "-preset", "ultrafast",
                            "-threads", "0", "-c:a", "aac", "-movflags", "+faststart", out)
    if rc != 0 or not os.path.exists(out):
        raise RuntimeError("ffmpeg convert video បរាជ័យ: " + err.decode("utf-8", "ignore")[:150])
    return out


async def _probe(path):
    meta = {"duration": None, "width": None, "height": None}
    if not shutil.which("ffprobe"):
        return meta
    try:
        rc, out, _ = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
                                "-of", "json", path)
        j = json.loads(out or b"{}")
        meta["duration"] = int(float(j.get("format", {}).get("duration", 0) or 0)) or None
        for st in j.get("streams", []):
            if st.get("width"):
                meta["width"], meta["height"] = st["width"], st["height"]
                break
    except Exception:
        pass
    return meta


async def _thumb(s, info_data, jobdir):
    """Download + shrink the cover (Telegram wants small JPEG)."""
    url = find_thumb(info_data) if info_data else None
    if not url:
        return None
    try:
        raw = os.path.join(jobdir, "thumb_raw")
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                return None
            with open(raw, "wb") as f:
                f.write(await r.read())
        if HAS_FFMPEG:
            out = os.path.join(jobdir, "thumb.jpg")
            rc, _, _ = await _run("ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-vf", "scale=320:-2",
                                  "-q:v", "5", out)
            if rc == 0 and os.path.exists(out):
                return out
        return raw
    except Exception as e:
        log.info("thumb failed: %s", e)
        return None


async def _via_api(url, kind, jobdir, progress, token):
    base = config.NUB_API_BASE.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    params = {config.NUB_API_URL_PARAM: url}
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=180)
    connector = aiohttp.TCPConnector(limit=PARTS * 3)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:

        async def get_info():
            try:
                async with s.get(base + config.NUB_INFO_PATH, params=params, headers=headers) as r:
                    if r.status == 200:
                        return await r.json(content_type=None)
            except Exception as e:
                log.info("info failed: %s", e)
            return None

        async def get_stream():
            # /stream normally returns JSON {"url":..., "stream_url": ".../stream/resolver/..."}
            async with s.get(base + config.NUB_STREAM_PATH, params=params, headers=headers,
                             allow_redirects=True) as r:
                if r.status != 200:
                    raise RuntimeError(f"stream HTTP {r.status}: {(await r.text())[:150]}")
                if not _is_text(r.headers.get("Content-Type", "")):
                    return "file", await _save(r, jobdir, progress)
                txt = await r.text()
            return "text", txt

        # info + stream-json run at the same time
        info_data, (skind, payload) = await asyncio.gather(get_info(), get_stream())
        title = find_title(info_data) if info_data else None
        thumb_task = asyncio.create_task(_thumb(s, info_data, jobdir))

        hops = 0
        while skind == "text":
            hops += 1
            if hops > 4:
                raise RuntimeError("តាម Link ច្រើនដងពេក នៅតែមិនបាន media: " + payload[:150])
            try:
                data = json.loads(payload)
            except Exception:
                data = None
            link = pick_link(data, url) if data else None
            if not link:
                m = re.search(r"https?://[^\s\"'<>]+", payload)
                link = m.group(0) if m and not any(h in m.group(0).lower() for h in _BAD_HOSTS) else None
            if not link:
                raise RuntimeError("គ្មានតំណ media ក្នុង JSON: " + payload[:200])
            skind, payload = await _fetch_media(s, link, headers, base, jobdir, progress)
        path = payload
        thumb = await thumb_task

    if os.path.getsize(path) < 20 * 1024:
        raise RuntimeError("ឯកសារតូចពេក (មិនមែន media)")
    fmt = sniff(path)
    if fmt == "text":
        raise RuntimeError("ទទួលបានទំព័រអក្សរ ជំនួស media")
    path = await _normalize(path, kind, fmt, jobdir)
    meta = await _probe(path)
    return {"path": path, "title": title or "media", "duration": meta["duration"],
            "width": meta["width"], "height": meta["height"], "thumb": thumb}


async def api_quota():
    token = await db.get_setting("nub_token", config.NUB_API_TOKEN)
    base = config.NUB_API_BASE.rstrip("/")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.get(base + "/rate-limit-status", headers={"Authorization": f"Bearer {token}"}) as r:
            return f"HTTP {r.status}\n" + (await r.text())[:800]


def cookies_path():
    return os.path.join(os.path.dirname(config.DB_PATH) or ".", "cookies.txt")


async def diagnose(url):
    token = await db.get_setting("nub_token", config.NUB_API_TOKEN)
    base = config.NUB_API_BASE.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    out = [f"token: {'មាន (' + str(len(token)) + ' តួ)' if token else 'គ្មាន'}"]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40)) as s:
        for name, path in (("info", config.NUB_INFO_PATH), ("stream", config.NUB_STREAM_PATH)):
            try:
                async with s.get(base + path, params={config.NUB_API_URL_PARAM: url}, headers=headers) as r:
                    ct = r.headers.get("Content-Type", "")
                    if name == "stream" and not (ct.startswith("text") or "json" in ct):
                        body = f"(media {r.headers.get('Content-Length', '?')} bytes)"
                    else:
                        body = (await r.text())[:400]
                    out.append(f"{name}: HTTP {r.status} {ct}\n{body}")
            except Exception as e:
                out.append(f"{name}: ERR {e}")
    return "\n\n".join(out)


def _ytdlp(url, kind, jobdir):
    opts = {
        "outtmpl": os.path.join(jobdir, "%(id)s.%(ext)s"),
        "noplaylist": True, "quiet": True, "no_warnings": True,
        "max_filesize": config.MAX_FILE, "retries": 5, "merge_output_format": "mp4",
    }
    cf = config.COOKIES_FILE or cookies_path()
    if os.path.exists(cf):
        opts["cookiefile"] = cf
    if kind == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        opts["format"] = "bv*[height<=1080]+ba/b[height<=1080]/b"
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
    files = [p for p in glob.glob(os.path.join(jobdir, "*")) if os.path.isfile(p)]
    if not files:
        raise RuntimeError("ទាញយកមិនបាន")
    path = max(files, key=os.path.getsize)
    return {"path": path, "title": info.get("title") or "media", "duration": info.get("duration"),
            "width": info.get("width"), "height": info.get("height")}


async def fetch(url, kind, jobdir, progress=None):
    os.makedirs(jobdir, exist_ok=True)
    token = await db.get_setting("nub_token", config.NUB_API_TOKEN)
    api_err = None
    if token:
        try:
            return await _via_api(url, kind, jobdir, progress, token)
        except Exception as e:
            api_err = str(e) or type(e).__name__
            log.warning("NUB API failed → fallback yt-dlp: %s", api_err)
            for p in glob.glob(os.path.join(jobdir, "*")):
                os.remove(p)
    try:
        return await asyncio.to_thread(_ytdlp, url, kind, jobdir)
    except Exception as e:
        msg = str(e).split("\n")[0]
        if "Sign in to confirm" in msg:
            msg = "YouTube ទប់ស្កាត់ IP របស់ Server (ត្រូវការ cookies)"
        raise RuntimeError(f"API: {(api_err or 'មិនបានដាក់ Token')[:380]} | yt-dlp: {msg[:70]}")
