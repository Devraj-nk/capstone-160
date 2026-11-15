"""Download every model the pipeline uses into backend/models/ (no Hugging Face cache).

    cd backend
    python tools/download_models.py            # all models
    python tools/download_models.py --check    # only report what is present

Resumes interrupted downloads (a stalled connection is retried from where it
stopped) and verifies each weights file against its SHA-256 from Hugging Face.
Afterwards the backend loads the models from disk and needs no network.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analysis.model_store import MODEL_REPOS, is_downloaded, local_dir  # noqa: E402

HF = "https://huggingface.co"
SKIP = {".gitattributes", "README.md"}
CHUNK = 1 << 20
STALL_SECONDS = 30
MAX_ATTEMPTS = 50


def repo_files(client: httpx.Client, repo_id: str) -> list[dict]:
    r = client.get(f"{HF}/api/models/{repo_id}/tree/main", params={"recursive": "true"})
    r.raise_for_status()
    return [f for f in r.json() if f.get("type") == "file" and f["path"] not in SKIP]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def fetch(client: httpx.Client, repo_id: str, info: dict, dest: Path) -> None:
    size, expected = info.get("size", 0), (info.get("lfs") or {}).get("oid")
    if dest.is_file() and dest.stat().st_size == size and (not expected or sha256(dest) == expected):
        print(f"  ok        {info['path']}")
        return
    part = dest.with_name(dest.name + ".part")
    if dest.is_file() and not part.exists():
        dest.rename(part)  # wrong size or hash: treat as a partial download
    url = f"{HF}/{repo_id}/resolve/main/{info['path']}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        have = part.stat().st_size if part.exists() else 0
        if have > size:
            part.unlink()
            have = 0
        if have == size:
            break
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with client.stream("GET", url, headers=headers, timeout=httpx.Timeout(STALL_SECONDS)) as r:
                if r.status_code == 200 and have:
                    have = 0  # server ignored the range: start over
                elif r.status_code not in (200, 206):
                    r.raise_for_status()
                last_print = 0.0
                with part.open("ab" if have else "wb") as fh:
                    for block in r.iter_bytes(CHUNK):
                        fh.write(block)
                        have += len(block)
                        now = time.monotonic()
                        if now - last_print > 5:
                            print(f"  {have / 1e6:8.0f} / {size / 1e6:.0f} MB  {info['path']}", flush=True)
                            last_print = now
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            print(f"  retry {attempt}: {type(exc).__name__} at {have / 1e6:.0f} MB", flush=True)
            time.sleep(min(2 * attempt, 15))
    else:
        raise RuntimeError(f"gave up on {repo_id}/{info['path']}")
    if expected and sha256(part) != expected:
        part.unlink()
        raise RuntimeError(f"checksum mismatch for {repo_id}/{info['path']} (deleted, run again)")
    part.replace(dest)
    print(f"  done      {info['path']} ({size / 1e6:.0f} MB, checksum ok)" if expected else f"  done      {info['path']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only report which models are present")
    args = parser.parse_args()

    for repo_id, role in MODEL_REPOS.items():
        print(f"{'present' if is_downloaded(repo_id) else 'MISSING':<8} {repo_id}  ({role}) -> {local_dir(repo_id)}")
    if args.check:
        return 0

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for repo_id in MODEL_REPOS:
            print(f"\n== {repo_id}")
            for info in repo_files(client, repo_id):
                dest = local_dir(repo_id) / info["path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                fetch(client, repo_id, info, dest)
    print("\nAll models downloaded. The backend now loads them from", local_dir("x/x").parent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
