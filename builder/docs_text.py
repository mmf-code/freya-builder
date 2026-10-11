"""Turn a folder of bank documents into files the builder can read, without knowing what the documents say.

Text files are copied as they are. Word, PDF and Excel files get a text copy next to the original:
- .docx, .doc, .rtf, .odt: macOS `textutil` (plain text);
- .pdf: `pdftotext -layout` (poppler);
- .xlsx, .xlsm: read with the standard library, one Markdown table per sheet. A number in a cell whose format is a
  date is written as an ISO date.
Images and PDFs are also kept as they are: the builder's model can read them. Nothing is dropped silently: a file
that cannot be converted is listed in the manifest with the reason."""
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TEXT = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".tsv", ".html", ".htm", ".xml"}
WORD = {".docx", ".doc", ".rtf", ".odt"}
SHEET = {".xlsx", ".xlsm"}
KEEP = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
DATE_FMT_IDS = set(range(14, 23)) | {45, 46, 47}


def flat_name(rel: Path) -> str:
    """A file name for workspace/briefs/: the path inside the case folder with '/' replaced, safe characters only."""
    name = "__".join(rel.parts)
    return re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def xlsx_to_markdown(path: Path) -> str:
    z = zipfile.ZipFile(path)
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    date_styles = set()
    if "xl/styles.xml" in names:
        st = ET.fromstring(z.read("xl/styles.xml"))
        custom = {int(f.get("numFmtId")): f.get("formatCode", "") for f in st.findall("m:numFmts/m:numFmt", NS)}
        for i, xf in enumerate(st.findall("m:cellXfs/m:xf", NS)):
            fid = int(xf.get("numFmtId", "0"))
            code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", custom.get(fid, "")).lower()
            if fid in DATE_FMT_IDS or (fid in custom and re.search(r"[dy]", code) and not re.search(r"[#0]", code)):
                date_styles.add(i)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = [f"<!-- text copy of {path.name}, one table per sheet -->"]
    for sh in wb.findall("m:sheets/m:sheet", NS):
        rid = sh.get(f"{{{NS['r']}}}id")
        t = target.get(rid, "")
        part = t.lstrip("/") if t.startswith("/") else "xl/" + t
        if part not in names:
            out.append(f"\n## Sheet: {sh.get('name')}\n\n(sheet part {part} not found)")
            continue
        rows = []
        for row in ET.fromstring(z.read(part)).iter(f"{{{NS['m']}}}row"):
            cells = {}
            for c in row.findall("m:c", NS):
                v = c.find("m:v", NS)
                kind = c.get("t")
                if kind == "s" and v is not None:
                    val = shared[int(v.text)]
                elif kind == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
                elif v is not None:
                    val = v.text or ""
                    if kind not in ("str", "b", "e") and int(c.get("s", "0")) in date_styles:
                        try:
                            d = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=float(val))
                            val = d.date().isoformat() if d.time() == datetime.time(0) else d.isoformat(timespec="minutes")
                        except (ValueError, OverflowError):
                            pass
                else:
                    val = ""
                cells[col_index(c.get("r", "A1"))] = val.replace("|", "\\|").replace("\n", " ")
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        out.append(f"\n## Sheet: {sh.get('name')}\n")
        if not rows:
            out.append("(empty)")
            continue
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        out.append("| " + " | ".join(rows[0]) + " |")
        out.append("|" + "---|" * width)
        out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out) + "\n"


def convert(case: Path, dest: Path) -> dict:
    """Write every usable file of `case` into `dest` (flat). Returns the manifest, also written to dest/../manifest.json."""
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {"case": str(case), "files": []}
    root = case.resolve()
    for src in sorted(p for p in case.rglob("*") if p.is_file()):
        rel = src.relative_to(case)
        if any(part.startswith(".") or part == "__MACOSX" for part in rel.parts):
            continue
        # A link, or a path that resolves outside the case folder, is never read: it could point at a secret.
        if any((case / Path(*rel.parts[:i + 1])).is_symlink() for i in range(len(rel.parts))) \
                or not src.resolve().is_relative_to(root):
            manifest["files"].append({"source": str(rel), "skipped": "symbolic link or outside the case folder: not read"})
            continue
        ext = src.suffix.lower()
        entry = {"source": str(rel), "sha256": sha256(src), "outputs": []}
        name = flat_name(rel)
        try:
            if ext in TEXT:
                shutil.copy2(src, dest / name)
                entry["outputs"].append(name)
            elif ext in WORD:
                txt = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(src)], capture_output=True, check=True).stdout
                (dest / (name + ".txt")).write_bytes(txt)
                entry["outputs"].append(name + ".txt")
            elif ext in SHEET:
                (dest / (name + ".md")).write_text(xlsx_to_markdown(src), encoding="utf-8")
                entry["outputs"].append(name + ".md")
            elif ext == ".pdf":
                txt = subprocess.run(["pdftotext", "-layout", str(src), "-"], capture_output=True, check=True).stdout
                (dest / (name + ".txt")).write_bytes(txt)
                shutil.copy2(src, dest / name)
                entry["outputs"] += [name + ".txt", name]
            elif ext in KEEP:
                shutil.copy2(src, dest / name)
                entry["outputs"].append(name)
            else:
                entry["skipped"] = f"no converter for {ext or 'files without an extension'}"
        except (subprocess.CalledProcessError, FileNotFoundError, zipfile.BadZipFile, ET.ParseError, KeyError) as e:
            entry["skipped"] = f"conversion failed: {type(e).__name__}: {str(e)[:200]}"
        manifest["files"].append(entry)
    return manifest


if __name__ == "__main__":
    m = convert(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(m, indent=1, ensure_ascii=False))
