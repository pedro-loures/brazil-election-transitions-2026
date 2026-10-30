"""Download official TSE bulk files, recording provenance and content hashes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    return s


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_one(resource, directory):
    url = resource["url"]
    if not url.startswith("https://cdn.tse.jus.br/"):
        raise ValueError(f"Unexpected download host: {url}")
    target = directory / url.rsplit("/", 1)[-1]
    if not target.exists():
        print(f"Downloading {url}", flush=True)
        temp = target.with_suffix(".zip.part")
        with session().get(url, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            total = 0
            with temp.open("wb") as f:
                for chunk in response.iter_content(8 * 1024 * 1024):
                    total += len(chunk)
                    if total > 2_000_000_000:
                        raise ValueError("Download exceeds 2 GB per-file limit")
                    f.write(chunk)
        if not zipfile.is_zipfile(temp):
            raise ValueError(f"Downloaded response is not a ZIP: {url}")
        temp.replace(target)
    result = {"url": url, "file": str(target), "bytes": target.stat().st_size,
              "sha256": sha256(target), "resource_name": resource["name"]}
    print(f"Ready {target.name}: {result['bytes']:,} bytes", flush=True)
    return result


def download(year, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    api = f"https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-{year}"
    response = session().get(api, timeout=60)
    response.raise_for_status()
    package = response.json()
    if not package.get("success"):
        raise ValueError(f"TSE dataset unavailable for {year}")
    (directory / "tse_metadata.json").write_text(
        json.dumps(package, indent=2, ensure_ascii=False))
    endings = [f"votacao_secao_{year}_BR.zip", f"detalhe_votacao_secao_{year}.zip",
               f"detalhe_votacao_munzona_{year}.zip", f"votacao_candidato_munzona_{year}.zip"]
    selected = []
    for ending in endings:
        found = [r for r in package["result"]["resources"] if r["url"].endswith("/" + ending)]
        if len(found) != 1:
            raise ValueError(f"Expected exactly one TSE resource for {ending}")
        selected.append(found[0])
    with ThreadPoolExecutor(max_workers=3) as pool:
        files = list(pool.map(lambda r: fetch_one(r, directory), selected))
    manifest = {"retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "year": year, "metadata_url": api, "files": files,
                "tse_notes": package["result"].get("notes")}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest
