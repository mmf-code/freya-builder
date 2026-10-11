"""Keep every download of the final case as its own snapshot. Show what changed since the previous one.

    python3 -I tools/case_snapshot.py ZIP

It writes case/_snapshots/sNN-<zip stamp>/ with:
- the zip, unchanged;
- inventory.json: path, size, zip time and sha256 of every file;
- diff.json: files added, removed and changed since the previous snapshot;
- extracted/: the files exactly as the zip holds them. This is what a build reads;
- inner/: a zip inside the zip, extracted one level deep, for us to read. A build does not see it.
Nobody changes a snapshot afterwards. A build names the extracted folder that it used.
This script does not read what the documents say."""
import hashlib
import io
import json
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def inventory(zf: zipfile.ZipFile, prefix: str = "") -> list[dict]:
    out = []
    for i in zf.infolist():
        if i.is_dir():
            continue
        b = zf.read(i)
        out.append({"path": prefix + i.filename, "size": i.file_size,
                    "zip_mtime": "%04d-%02d-%02d %02d:%02d" % i.date_time[:5],
                    "sha256": hashlib.sha256(b).hexdigest()})
        if i.filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(b)) as inner:
                    out += inventory(inner, prefix + i.filename + "!/")
            except zipfile.BadZipFile:
                pass
    return out


def extract(zp: Path, snap: Path) -> None:
    with zipfile.ZipFile(zp) as zf:
        zf.extractall(snap / "extracted")  # zipfile drops absolute paths and '..' parts
    for inner in sorted((snap / "extracted").rglob("*.zip")):
        rel = inner.relative_to(snap / "extracted")
        try:
            with zipfile.ZipFile(inner) as zf:
                zf.extractall(snap / "inner" / rel.with_suffix(""))
        except zipfile.BadZipFile:
            print(f"case_snapshot: not a zip: {rel}")


def main() -> int:
    zp = Path(sys.argv[1]).resolve()
    snaps = ROOT / "case" / "_snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    zsha = hashlib.sha256(zp.read_bytes()).hexdigest()
    previous = {p.name: json.loads((p / "inventory.json").read_text())
                for p in sorted(snaps.iterdir()) if (p / "inventory.json").is_file()}
    for name, inv in previous.items():
        if inv["zip_sha256"] == zsha:
            print(f"case_snapshot: same zip as {name}; nothing new")
            return 0
    last = list(previous)[-1] if previous else None
    m = re.search(r"\d{8}T\d{6}Z", zp.name)  # Google Drive puts the download time (UTC) in the zip name
    snap = snaps / f"s{len(previous) + 1:02d}-{m.group(0) if m else time.strftime('%Y%m%dT%H%M%S')}"
    snap.mkdir()
    shutil.copy2(zp, snap / zp.name)
    with zipfile.ZipFile(zp) as zf:
        files = inventory(zf)
    extract(snap / zp.name, snap)

    old = {f["path"]: f for f in previous[last]["files"]} if last else {}
    new = {f["path"]: f for f in files}
    diff = {"against": last,
            "added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
            "changed": sorted(p for p in new.keys() & old.keys() if new[p]["sha256"] != old[p]["sha256"])}
    (snap / "diff.json").write_text(json.dumps(diff, indent=1, ensure_ascii=False), encoding="utf-8")
    # inventory.json last: a snapshot without it does not count as a previous one
    inv = {"snapshot": snap.name, "source": str(zp), "taken_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "zip_sha256": zsha, "files": files}
    (snap / "inventory.json").write_text(json.dumps(inv, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"case_snapshot: {snap.relative_to(ROOT)}: {len(files)} files; against {diff['against']}: "
          f"{len(diff['added'])} added, {len(diff['removed'])} removed, {len(diff['changed'])} changed")
    for k in ("added", "removed", "changed"):
        for p in diff[k]:
            print(f"  {k}: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
