"""Harvest real Talend job files (.item) from public GitHub repositories to
grow samples/talend/ — the parser's real-world variety test.

Same discipline as the Crystal corpus harvest:
  * search by COMPONENT name (not just the root tag) so results spread across
    job styles instead of hitting the 1000-result cap on one query;
  * cap files per repository so no single project dominates;
  * verify every candidate by PARSING it — a file only lands if the real
    TalendParser accepts it;
  * hash-dedupe (the same job is often forked/vendored);
  * record provenance (repo, path, license, sha) in MANIFEST.md.

Usage:
  python scripts/harvest_talend.py --target 120          # add up to 120 jobs
  python scripts/harvest_talend.py --target 40 --dry-run

Needs the gh CLI authenticated (`gh auth status`).
"""

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "samples" / "talend"
MANIFEST = OUT_DIR / "MANIFEST.md"

# Component-name queries: each surfaces a different slice of the ecosystem
# (database jobs, file jobs, orchestration, ESB, big data...).
QUERIES = [
    "talendfile+extension:item",
    "tMap+extension:item",
    "tFileInputDelimited+extension:item",
    "tFileOutputDelimited+extension:item",
    "tPostgresqlInput+extension:item",
    "tMysqlInput+extension:item",
    "tOracleInput+extension:item",
    "tMSSqlInput+extension:item",
    "tAggregateRow+extension:item",
    "tFilterRow+extension:item",
    "tRunJob+extension:item",
    "tJavaRow+extension:item",
    "tXMLMap+extension:item",
    "tHashOutput+extension:item",
    "tRESTClient+extension:item",
    "tSetGlobalVar+extension:item",
]

PER_REPO_CAP = 6
MAX_BYTES = 3_000_000       # skip absurd generated jobs
SEARCH_PAUSE = 2.5          # code search is rate-limited (~30/min)


def gh_api(path, retries=3):
    for attempt in range(retries):
        proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        if "rate limit" in proc.stderr.lower() or "403" in proc.stderr:
            wait = 20 * (attempt + 1)
            print(f"    rate limited, waiting {wait}s...", flush=True)
            time.sleep(wait)
            continue
        return None
    return None


def search_candidates(target):
    """{(owner/repo, path)} -> candidate list, spread across queries."""
    seen, candidates = set(), []
    for query in QUERIES:
        if len(candidates) >= target * 4:  # over-collect; many will fail checks
            break
        for page in (1, 2):
            data = gh_api(f"search/code?q={query}&per_page=100&page={page}")
            time.sleep(SEARCH_PAUSE)
            if not data or not data.get("items"):
                break
            for item in data["items"]:
                repo = item["repository"]["full_name"]
                key = (repo, item["path"])
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({"repo": repo, "path": item["path"],
                                   "url": item["url"]})
            print(f"  {query} page {page}: {len(candidates)} candidates so far",
                  flush=True)
    return candidates


def fetch_content(repo, path):
    data = gh_api(f"repos/{repo}/contents/{path.replace(' ', '%20')}")
    if not data or data.get("encoding") != "base64":
        return None
    if data.get("size", 0) > MAX_BYTES:
        return None
    try:
        return base64.b64decode(data["content"])
    except Exception:
        return None


def repo_license(repo, cache={}):
    if repo not in cache:
        data = gh_api(f"repos/{repo}")
        cache[repo] = ((data or {}).get("license") or {}).get("spdx_id") or "NOASSERTION"
        time.sleep(0.3)
    return cache[repo]


def parses(path):
    """A candidate is only kept if the REAL parser accepts it."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from pentaho_migration.parser import TalendParser

    try:
        pipelines = TalendParser().parse_file(path)
    except Exception:
        return False
    return bool(pipelines and pipelines[0].steps)


def safe_name(repo, path):
    owner = repo.split("/")[0]
    stem = Path(path).name
    return re.sub(r"[^\w.\-]+", "_", f"{owner}_{stem}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=100, help="new jobs to add")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing_hashes = {hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in OUT_DIR.glob("*.item")}
    existing_names = {p.name for p in OUT_DIR.glob("*.item")}
    print(f"existing corpus: {len(existing_names)} jobs")

    candidates = search_candidates(args.target)
    print(f"\n{len(candidates)} unique candidates found; verifying...\n")

    per_repo, added, manifest_rows = {}, 0, []
    tmp = OUT_DIR / "_candidate.tmp"
    for cand in candidates:
        if added >= args.target:
            break
        repo, path = cand["repo"], cand["path"]
        if per_repo.get(repo, 0) >= PER_REPO_CAP:
            continue
        name = safe_name(repo, path)
        if name in existing_names:
            continue
        blob = fetch_content(repo, path)
        time.sleep(0.35)
        if not blob or b"ProcessType" not in blob[:4000]:
            continue
        digest = hashlib.sha256(blob).hexdigest()
        if digest in existing_hashes:
            continue
        tmp.write_bytes(blob)
        if not parses(tmp):
            continue
        target_path = OUT_DIR / name
        if args.dry_run:
            print(f"  [dry-run] would add {name}  ({repo}/{path})")
        else:
            target_path.write_bytes(blob)
        existing_hashes.add(digest)
        existing_names.add(name)
        per_repo[repo] = per_repo.get(repo, 0) + 1
        added += 1
        manifest_rows.append((name, repo, path, repo_license(repo), digest[:12]))
        print(f"  + {name}  ({repo})", flush=True)
    tmp.unlink(missing_ok=True)

    print(f"\nadded {added} job(s); corpus now {len(existing_names)} files")
    if manifest_rows and not args.dry_run:
        header = ("# Talend corpus provenance\n\n"
                  "Real `.item` job files harvested from public GitHub repositories "
                  "for parser/rules validation. Each was verified by parsing it with "
                  "the project's own TalendParser; per-repository cap "
                  f"{PER_REPO_CAP}. Regenerate/extend with "
                  "`python scripts/harvest_talend.py --target N`.\n\n"
                  "| File | Repository | Path | License | sha256 |\n"
                  "| --- | --- | --- | --- | --- |\n")
        body = "".join(f"| `{n}` | [{r}](https://github.com/{r}) | `{p}` | {lic} | `{h}` |\n"
                       for n, r, p, lic, h in manifest_rows)
        if MANIFEST.exists():
            MANIFEST.write_text(MANIFEST.read_text(encoding="utf-8") + body,
                                encoding="utf-8")
        else:
            MANIFEST.write_text(header + body, encoding="utf-8")
        print(f"provenance appended to {MANIFEST.relative_to(REPO_ROOT)}")
    print("\nNext: pentaho-migrate gaps samples/talend")


if __name__ == "__main__":
    main()
