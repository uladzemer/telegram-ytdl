import sys
import json
import re
import html
import os
import subprocess
from urllib.parse import urlsplit, urlunsplit, parse_qsl, parse_qs, urlencode


def clean_url(value):
    if not value:
        return value
    value = value.replace("\\u0026", "&").replace("\\u002F", "/")
    value = value.replace("\\/", "/")
    return html.unescape(value)


def strip_byte_range(value):
    if not value:
        return value
    try:
        parsed = urlsplit(value)
        if "fbcdn.net" not in parsed.netloc:
            return value
        if ".mp4" not in parsed.path.lower():
            return value
        query = [
            (k, v)
            for (k, v) in parse_qsl(parsed.query, keep_blank_values=True)
            if k not in ("bytestart", "byteend")
        ]
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query, doseq=True),
                parsed.fragment,
            )
        )
    except Exception:
        return value


def first_json_url(text, keys):
    for key in keys:
        match = re.search(r'"%s"\s*:\s*"([^"]+)"' % re.escape(key), text)
        if match:
            return clean_url(match.group(1))
    return None


def extract_mp4_urls(text):
    urls = []
    for match in re.findall(r'https?://[^\\s"\'\\\\]+?\\.mp4[^\\s"\'\\\\]*', text):
        urls.append(clean_url(match))
    for match in re.findall(r'https?:\\\\/\\\\/[^\\s"\\\\]+?\\.mp4[^\\s"\\\\]*', text):
        urls.append(clean_url(match))
    return urls


def pick_best_url(candidates):
    if not candidates:
        return None
    # Prefer video.fbcdn.net over scontent
    def score(url):
        host = ""
        try:
            host = urlsplit(url).netloc.lower()
        except Exception:
            host = ""
        score = 0
        if host.startswith("video."):
            score += 3
        if "fbcdn.net" in host:
            score += 2
        if "scontent" in host:
            score += 1
        return score

    return max(candidates, key=score)


def extract_story_fbid(url):
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        value = query.get("story_fbid", [None])[0]
        return str(value) if value else None
    except Exception:
        return None


def extract_story_user_id(url):
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        value = query.get("id", [None])[0]
        return str(value) if value else None
    except Exception:
        return None


def match_story_id(value, story_id):
    if value is None or story_id is None:
        return False
    try:
        return str(value) == str(story_id)
    except Exception:
        return False


def extract_story_params_from_text(text):
    if not text:
        return None, None
    # Common URL forms in HTML/JS blobs
    match = re.search(r'story_fbid=(\d+)&id=(\d+)', text)
    if match:
        return match.group(1), match.group(2)
    match = re.search(r'"story_fbid"\s*:\s*"(\d+)"', text)
    if match:
        return match.group(1), None
    match = re.search(r'story_fbid%3D(\d+)%26id%3D(\d+)', text)
    if match:
        return match.group(1), match.group(2)
    match = re.search(r'story_fbid=(\d+)', text)
    if match:
        return match.group(1), None
    return None, None


def build_story_url(story_fbid, user_id=None):
    if not story_fbid:
        return None
    if user_id:
        return f"https://www.facebook.com/story.php?story_fbid={story_fbid}&id={user_id}"
    return f"https://www.facebook.com/story.php?story_fbid={story_fbid}"


def extract_meta_url(text):
    if not text:
        return None
    patterns = [
        r'property=["\']og:url["\'][^>]*content=["\']([^"\']+)["\']',
        r'content=["\']([^"\']+)["\'][^>]*property=["\']og:url["\']',
        r'rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
        r'href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match and match.group(1):
            return clean_url(match.group(1).strip())
    return None


def should_refetch_resolved_url(value):
    if not value:
        return False
    try:
        parsed = urlsplit(value)
        if not parsed.netloc.lower().endswith("facebook.com"):
            return False
        path = parsed.path.lower()
        return (
            path.startswith("/reel/")
            or path == "/watch"
            or path == "/story.php"
            or path.startswith("/story.php")
        )
    except Exception:
        return False


def is_facebook_consent_url(value):
    if not value:
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.netloc.lower()
        if not host.endswith("facebook.com"):
            return False
        path = parsed.path.lower()
        if path.startswith("/privacy/consent"):
            return True
        query = parse_qs(parsed.query)
        flow = (query.get("flow") or [None])[0]
        return isinstance(flow, str) and "ad_free_subscription" in flow.lower()
    except Exception:
        return False


def is_temporary_block_page(text):
    if not text:
        return False
    lowered = text.lower()
    markers = [
        "temporarily blocked",
        "you have been temporarily blocked",
        "you used this feature too often",
        "вы временно заблокированы",
        "слишком часто использовали эту функцию",
        "\\u0432\\u0440\\u0435\\u043c\\u0435\\u043d\\u043d\\u043e",
        "\\u0437\\u0430\\u0431\\u043b\\u043e\\u043a\\u0438\\u0440\\u043e\\u0432",
        "\\u0441\\u043b\\u0438\\u0448\\u043a\\u043e\\u043c \\u0447\\u0430\\u0441\\u0442\\u043e",
        "cometerrorroot.react",
    ]
    return any(marker in lowered for marker in markers)


def find_story_objects(obj, story_id, results):
    if isinstance(obj, dict):
        # Direct match on common keys
        for key in ("story_fbid", "story_id", "storyId", "story_legacy_id"):
            if match_story_id(obj.get(key), story_id):
                results.append(obj)
                break
        # Recurse
        for value in obj.values():
            find_story_objects(value, story_id, results)
    elif isinstance(obj, list):
        for value in obj:
            find_story_objects(value, story_id, results)


def extract_urls_from_obj(obj):
    urls = []
    if isinstance(obj, dict):
        for key in (
            "playable_url_quality_hd",
            "browser_native_hd_url",
            "playable_url_quality_sd",
            "browser_native_sd_url",
            "playable_url",
            "playback_url",
            "video_url",
            "dash_manifest_url",
        ):
            value = obj.get(key)
            if isinstance(value, str) and value.startswith("http"):
                urls.append(clean_url(value))
        # video_versions array
        versions = obj.get("video_versions") or obj.get("video_versions2")
        if isinstance(versions, list):
            for item in versions:
                if isinstance(item, dict):
                    value = item.get("url")
                    if isinstance(value, str) and value.startswith("http"):
                        urls.append(clean_url(value))
        # Recurse
        for value in obj.values():
            urls.extend(extract_urls_from_obj(value))
    elif isinstance(obj, list):
        for value in obj:
            urls.extend(extract_urls_from_obj(value))
    return urls


def pick_best_story_url(candidates):
    if not candidates:
        return None
    # Prefer HD playable urls and fbcdn video hosts
    def score(url):
        score = 0
        lowered = url.lower()
        if "playable_url_quality_hd" in lowered:
            score += 4
        if "hd" in lowered:
            score += 2
        try:
            host = urlsplit(url).netloc.lower()
        except Exception:
            host = ""
        if host.startswith("video."):
            score += 3
        if "fbcdn.net" in host:
            score += 2
        if ".mpd" in lowered or "dash" in lowered:
            score -= 1
        return score

    return max(candidates, key=score)


def to_mbasic_url(value):
    if not value:
        return value
    try:
        parsed = urlsplit(value)
        host = parsed.netloc.lower()
        if not host.endswith("facebook.com"):
            return value
        return urlunsplit(
            (
                parsed.scheme or "https",
                "mbasic.facebook.com",
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )
    except Exception:
        return value


def extract_video_redirect_src(text):
    if not text:
        return None
    # /video_redirect/?src=<encoded_video_url>
    for match in re.findall(r'href=["\']([^"\']*?/video_redirect/\?[^"\']+)["\']', text, re.IGNORECASE):
        candidate = clean_url(match)
        if candidate.startswith("/"):
            candidate = f"https://mbasic.facebook.com{candidate}"
        try:
            parsed = urlsplit(candidate)
            query = parse_qs(parsed.query)
            src = (query.get("src") or [None])[0]
            if isinstance(src, str) and src.startswith("http"):
                return clean_url(src)
        except Exception:
            continue
    return None


def resolve_story(url, cookie_file=None, proxy_file=None):
    headers = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("Sec-Fetch-Site", "none"),
        ("Sec-Fetch-Mode", "navigate"),
        ("Sec-Fetch-User", "?1"),
        ("Sec-Fetch-Dest", "document"),
    ]

    proxy = ""
    if proxy_file and os.path.exists(proxy_file):
        with open(proxy_file, "r") as f:
            proxy = f.read().strip()
    proxy = proxy or os.environ.get("YTDL_PROXY", "").strip()

    def build_curl_args(target_url):
        args = ["curl", "-sL", "--compressed"]
        for key, value in headers:
            args.extend(["-H", f"{key}: {value}"])
        if cookie_file and os.path.exists(cookie_file):
            args.extend(["-b", cookie_file])
        if proxy:
            args.extend(["-x", proxy])
        args.append(target_url)
        return args

    def build_curl_effective_args(target_url):
        args = ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "%{url_effective}"]
        for key, value in headers:
            args.extend(["-H", f"{key}: {value}"])
        if cookie_file and os.path.exists(cookie_file):
            args.extend(["-b", cookie_file])
        if proxy:
            args.extend(["-x", proxy])
        args.append(target_url)
        return args

    def fetch_page(target_url):
        args = build_curl_args(target_url)
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            return None, {"error": f"curl failed: {e}"}
        if result.returncode != 0:
            return None, {"error": f"curl exit {result.returncode}: {result.stderr.strip()}"}
        return result.stdout, None

    def resolve_effective_url(target_url):
        args = build_curl_effective_args(target_url)
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except Exception:
            return target_url
        if result.returncode != 0:
            return target_url
        resolved = (result.stdout or "").strip()
        if not resolved:
            return target_url
        return clean_url(resolved)

    def try_mbasic_fallback(target_url):
        mbasic_url = to_mbasic_url(target_url)
        text_mbasic, fallback_error = fetch_page(mbasic_url)
        if fallback_error or not text_mbasic:
            return None

        src_candidate = extract_video_redirect_src(text_mbasic)
        if src_candidate:
            return {"video_url": strip_byte_range(src_candidate), "title": "Facebook Story"}

        keys = [
            "playable_url_quality_hd",
            "browser_native_hd_url",
            "playable_url_quality_sd",
            "browser_native_sd_url",
            "playable_url",
            "playback_url",
            "video_url",
        ]
        json_candidate = first_json_url(text_mbasic, keys)
        if json_candidate:
            return {"video_url": strip_byte_range(json_candidate), "title": "Facebook Story"}

        mp4_urls = [u for u in extract_mp4_urls(text_mbasic) if "fbcdn.net" in u]
        picked = pick_best_story_url(mp4_urls) or pick_best_url(mp4_urls)
        if picked:
            return {"video_url": strip_byte_range(picked), "title": "Facebook Story"}

        return None

    initial_url = resolve_effective_url(url)
    if is_facebook_consent_url(initial_url):
        mbasic_result = try_mbasic_fallback(url)
        if mbasic_result:
            return mbasic_result
        return {
            "error": "Facebook temporarily blocked this action for the current account/IP. Please wait and retry."
        }
    if should_refetch_resolved_url(initial_url):
        url = initial_url

    text, error = fetch_page(url)
    if error:
        mbasic_result = try_mbasic_fallback(url)
        if mbasic_result:
            return mbasic_result
        return error
    if is_temporary_block_page(text):
        mbasic_result = try_mbasic_fallback(url)
        if mbasic_result:
            return mbasic_result
        return {
            "error": "Facebook temporarily blocked this action for the current account/IP. Please wait and retry."
        }

    meta_url = extract_meta_url(text)
    if is_facebook_consent_url(meta_url):
        mbasic_result = try_mbasic_fallback(url)
        if mbasic_result:
            return mbasic_result
        return {
            "error": "Facebook temporarily blocked this action for the current account/IP. Please wait and retry."
        }
    if should_refetch_resolved_url(meta_url) and clean_url(meta_url) != clean_url(url):
        url = clean_url(meta_url)
        text, error = fetch_page(url)
        if error:
            mbasic_result = try_mbasic_fallback(url)
            if mbasic_result:
                return mbasic_result
            return error
        if is_temporary_block_page(text):
            mbasic_result = try_mbasic_fallback(url)
            if mbasic_result:
                return mbasic_result
            return {
                "error": "Facebook temporarily blocked this action for the current account/IP. Please wait and retry."
            }

    story_fbid = extract_story_fbid(url)
    story_user_id = extract_story_user_id(url)
    if not story_fbid:
        story_fbid, story_user_id = extract_story_params_from_text(text)

    # If we discovered a story id from a share/reel page, refetch story.php
    if story_fbid and "/story.php" not in url:
        story_url = build_story_url(story_fbid, story_user_id)
        if story_url:
            text, error = fetch_page(story_url)
            if error:
                mbasic_result = try_mbasic_fallback(story_url)
                if mbasic_result:
                    return mbasic_result
                return error
            if is_temporary_block_page(text):
                mbasic_result = try_mbasic_fallback(story_url)
                if mbasic_result:
                    return mbasic_result
                return {
                    "error": "Facebook temporarily blocked this action for the current account/IP. Please wait and retry."
                }

    # 1. Try to parse JSON payloads for the exact story
    if story_fbid:
        scripts = re.findall(
            r'<script[^>]*type="application/json"[^>]*data-sjs[^>]*>(.*?)</script>',
            text,
            re.DOTALL,
        )
        story_candidates = []
        for script in scripts:
            if "RelayPrefetchedStreamCache" not in script and story_fbid not in script:
                continue
            try:
                payload = json.loads(script)
            except Exception:
                continue
            story_objs = []
            find_story_objects(payload, story_fbid, story_objs)
            for obj in story_objs:
                story_candidates.extend(extract_urls_from_obj(obj))
        if story_candidates:
            picked = pick_best_story_url(story_candidates)
            if picked:
                return {"video_url": strip_byte_range(picked), "title": "Facebook Story"}

        # Fallback: search around story id in raw HTML
        if story_fbid in text:
            idx = text.find(story_fbid)
            start = max(0, idx - 20000)
            end = min(len(text), idx + 20000)
            snippet = text[start:end]
            keys = [
                "playable_url_quality_hd",
                "browser_native_hd_url",
                "playable_url_quality_sd",
                "browser_native_sd_url",
                "playable_url",
                "playback_url",
                "video_url",
            ]
            url_candidate = first_json_url(snippet, keys)
            if url_candidate:
                return {
                    "video_url": strip_byte_range(url_candidate),
                    "title": "Facebook Story",
                }

        # If we know the exact story id, do not fall back to generic page-level parsing,
        # otherwise we may return an unrelated video from the feed/login page.
        return {
            "error": "Could not find exact story video by story_fbid. Please ensure valid cookies for this account."
        }

    # 2. Look for explicit JSON urls (any story)
    keys = [
        "playable_url_quality_hd",
        "browser_native_hd_url",
        "playable_url_quality_sd",
        "browser_native_sd_url",
        "playable_url",
        "playback_url",
        "video_url",
    ]
    url_candidate = first_json_url(text, keys)
    if url_candidate:
        return {"video_url": strip_byte_range(url_candidate), "title": "Facebook Story"}

    # 3. og:video
    match = re.search(r'property="og:video" content="(.*?)"', text)
    if match:
        return {"video_url": strip_byte_range(clean_url(match.group(1))), "title": "Facebook Story"}

    match = re.search(r'property="og:video:secure_url" content="(.*?)"', text)
    if match:
        return {"video_url": strip_byte_range(clean_url(match.group(1))), "title": "Facebook Story"}

    # 4. Any fbcdn mp4 links in HTML
    mp4_urls = [u for u in extract_mp4_urls(text) if "fbcdn.net" in u]
    picked = pick_best_url(mp4_urls)
    if picked:
        return {"video_url": strip_byte_range(picked), "title": "Facebook Story"}

    return {"error": "Could not find video link in Facebook story page. Please ensure you uploaded valid cookies."}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}))
        sys.exit(1)

    url = sys.argv[1]
    cookie_file = sys.argv[2] if len(sys.argv) > 2 else "/app/storage/cookies.txt"
    proxy_file = sys.argv[3] if len(sys.argv) > 3 else "/app/storage/proxy.txt"
    print(json.dumps(resolve_story(url, cookie_file, proxy_file)))
