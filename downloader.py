#!/usr/bin/env python3
"""
闲鱼资源包下载器 v4 - 分阶段运行
Step1: 采集所有资源URL，保存到 urls.json
Step2: 从 urls.json 读取并下载（断点续传）
代理: http://127.0.0.1:7890
反爬: UA轮换/随机延迟/指数退避/并发3线程
"""
import os, sys, time, json, random, socket, gzip, re, logging, argparse
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request, urllib.error, ssl

# ========== 配置 ==========
PROXY = "http://127.0.0.1:7890"
BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
URLS_FILE = BASE_DIR / "urls.json"
TIMEOUT = 15
MAX_WORKERS = 3
MIN_DELAY = 1.5
MAX_DELAY = 4.0
MAX_RETRIES = 3
socket.setdefaulttimeout(15)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("dl")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
LANG_POOL = ["en-US,en;q=0.9", "en-US,en;q=0.9,zh-CN;q=0.8", "en-GB,en;q=0.9"]

def headers() -> dict:
    return {
        "User-Agent": random.choice(UA_POOL),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(LANG_POOL),
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1", "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1",
    }

def make_opener():
    ph = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    return urllib.request.build_opener(ph, urllib.request.HTTPSHandler(context=SSL_CTX))

def fetch(url: str, retries=MAX_RETRIES) -> str:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers())
            with make_opener().open(req, timeout=TIMEOUT) as r:
                raw = r.read()
                if raw[:2] == b'\x1f\x8b':
                    raw = gzip.decompress(raw)
                for enc in ('utf-8', 'utf-8-sig', 'euc-jp', 'shift-jis'):
                    try: return raw.decode(enc, errors='strict')
                    except (UnicodeDecodeError, LookupError): continue
                return raw.decode('utf-8', errors='ignore')
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(float(e.headers.get("Retry-After", 5*(attempt+1))))
            elif attempt < retries - 1:
                time.sleep(2**attempt + random.random())
        except Exception:
            if attempt < retries - 1:
                time.sleep(2**attempt + random.random())
    return ""

def download(url: str, path: Path, desc: str = "") -> bool:
    if path.exists():
        return True
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=headers())
            with make_opener().open(req, timeout=TIMEOUT) as r:
                content = r.read()
            if len(content) < 1024:
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            log.info(f"  ✅ {desc or path.name}: {len(content)/1024:.0f}KB")
            return True
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt + random.random())
    return False

def delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

# ========== 采集器 ==========

def crawl_all() -> list:
    """采集所有资源URL"""
    resources = []

    # --- printkids unpitsu: 控笔/迷宫/涂色 ---
    log.info("\n=== 源1: printkids（控笔/迷宫/涂色）===")
    resources.extend(crawl_printkids())

    # --- kidsactivities ---
    log.info("\n=== 源2: kidsactivities ===")
    resources.extend(crawl_kidsactivities())

    # --- readingbyphonics ---
    log.info("\n=== 源3: readingbyphonics ===")
    resources.extend(crawl_readingbyphonics())

    # 去重
    seen, unique = set(), []
    for u, f in resources:
        if u not in seen:
            seen.add(u)
            unique.append((u, f))
    return unique

def crawl_printkids() -> list:
    base = "https://print-kids.net"
    listing_url = f"{base}/print/unpitsu/"
    html = fetch(listing_url)
    if not html:
        log.warning("  ❌ unpitsu 列表页失败")
        return []

    all_subs = re.findall(r'href="([^"/]+/)"\s*>', html)
    all_subs = list(dict.fromkeys(s for s in all_subs if s and not s.startswith('#')))

    TARGET = {
        'nazorigaki': '控笔描红', 'meiro': '迷宫',
        'illust-meiro': '涂色迷宫', 'shiritori-meiro': '涂色迷宫',
        'hiragana-meiro': '迷宫', 'katakana-meiro': '迷宫',
        'aiueo-nurie': '涂色', 'katakana-nurie': '涂色',
    }
    target = [s for s in all_subs if s.rstrip('/') in TARGET]
    log.info(f"  📂 unpitsu: 目标{len(target)}/{len(all_subs)}个子页")

    resources = []
    for sub in target:
        name = TARGET[sub.rstrip('/')]
        item_url = f"{base}/print/unpitsu/{sub}"
        delay()
        try:
            item_html = fetch(item_url)
            if len(item_html) < 500:
                continue
            pdfs = re.findall(r'href="([^"\']+\.pdf)"', item_html)
            for pdf in pdfs:
                if pdf.startswith('http'):
                    full = pdf
                elif pdf.startswith('/'):
                    full = base + pdf
                else:
                    full = f"{base}/print/unpitsu/{sub}{pdf}"
                resources.append((full, f"printkids/{name}"))
        except Exception:
            pass

    log.info(f"  📦 printkids: {len(resources)} 个PDF")
    return resources

def crawl_kidsactivities() -> list:
    base = "https://www.kidsactivities.online"
    html = fetch(f"{base}/post-sitemap.xml")
    if not html:
        log.warning("  ❌ sitemap 失败")
        return []

    locs = re.findall(r'<loc>(.*?)</loc>', html)
    locs = [u for u in locs if '/feed/' not in u and '/page/' not in u]
    KEYS = ['phonics', 'reading', 'kindergarten', 'preschool', 'science',
            'math', 'tracing', 'alphabet', 'number', 'letter', 'stem',
            'coloring', 'craft', 'activity', 'worksheet']
    good = [u for u in locs if any(k in u.lower() for k in KEYS)]
    log.info(f"  📋 sitemap: {len(locs)}篇, 筛选高价值: {len(good)}篇")

    resources = []
    for i, url in enumerate(good):
        page_html = fetch(url)
        if not page_html:
            continue
        pdfs = re.findall(
            r'href="(https://www\.kidsactivities\.online/wp-content/uploads/[^"\'>\s]+\.pdf[^"\'>\s]*)"',
            page_html
        )
        folder = urlparse(url).path.strip('/').split('/')[-1][:25] or f"p{i}"
        for pdf in set(p.split('?')[0] for p in pdfs):
            resources.append((pdf, f"kidsactivities/{folder}"))
        if (i+1) % 25 == 0:
            log.info(f"  进度: {i+1}/{len(good)}, 已找到 {len(resources)} PDF")
        delay()

    seen, unique = set(), []
    for u, f in resources:
        if u not in seen:
            seen.add(u)
            unique.append((u, f))
    log.info(f"  📦 kidsactivities: {len(unique)} 个PDF")
    return unique

def crawl_readingbyphonics() -> list:
    base = "https://readingbyphonics.com"
    PAGES = [
        ("/worksheets/alphabet-letter-flashcards.html", "字母闪卡"),
        ("/worksheets/abc-printable-sheets.html", "字母练习"),
        ("/worksheets/pre-k-phonics-printables.html", "拼读练习"),
        ("/worksheets/220-dolch-sight-words.html", "高频词"),
    ]
    resources = []
    for path, name in PAGES:
        html = fetch(base + path)
        if not html:
            continue
        pdfs = re.findall(r'href="(/wp-content/uploads/[^"\'>\s]+\.pdf[^"\'>\s]*)"', html)
        for pdf in pdfs:
            resources.append((base + pdf, f"readingbyphonics/{name}"))
        delay()

    seen, unique = set(), []
    for u, f in resources:
        if u not in seen:
            seen.add(u)
            unique.append((u, f))
    log.info(f"  📦 readingbyphonics: {len(unique)} 个PDF")
    return unique

# ========== 下载器 ==========

def download_all(resources: list):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"\n=== 下载 {len(resources)} 个文件 ===")
    log.info(f"📁 {DOWNLOAD_DIR}")

    random.shuffle(resources)
    downloaded, failed = 0, []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for url, folder in resources:
            fn = url.split("/")[-1].split("?")[0]
            if not fn.lower().endswith(".pdf"):
                fn += ".pdf"
            path = DOWNLOAD_DIR / folder / fn
            if path.exists():
                continue
            future = pool.submit(download, url, path, f"{folder}/{fn}")
            futures[future] = (url, folder)

        for future in as_completed(futures):
            url, folder = futures[future]
            try:
                if future.result():
                    downloaded += 1
                else:
                    failed.append((url, folder))
            except Exception:
                failed.append((url, folder))
            time.sleep(random.uniform(0.3, 1.0))

    log.info(f"\n✅ 完成: {downloaded}/{len(resources)} 成功，{len(failed)} 失败")

    # 统计
    from collections import Counter
    counts = Counter(f for _, f in resources)
    for k, v in counts.items():
        done = len(list((DOWNLOAD_DIR / k).glob("*.pdf")))
        log.info(f"  {k}: {done}/{v}")

    # 保存失败列表
    if failed:
        fail_file = DOWNLOAD_DIR / "failed.json"
        fail_file.write_text(json.dumps([(u, f) for u, f in failed], ensure_ascii=False))

# ========== 入口 ==========

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["crawl", "download", "all"], default="all")
    args = ap.parse_args()

    if args.step in ("crawl", "all"):
        log.info("=== Step1: 采集资源URL ===")
        resources = crawl_all()
        log.info(f"\n✅ 共采集 {len(resources)} 个唯一URL")
        URLS_FILE.write_text(json.dumps(resources, ensure_ascii=False, indent=2))
        log.info(f"   已保存: {URLS_FILE}")

    if args.step in ("download", "all"):
        if not URLS_FILE.exists():
            log.error("urls.json 不存在，请先运行 --step crawl")
            return
        resources = json.loads(URLS_FILE.read_text())
        download_all(resources)

if __name__ == "__main__":
    random.seed()
    main()
