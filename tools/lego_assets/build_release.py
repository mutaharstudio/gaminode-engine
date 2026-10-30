#!/usr/bin/env python3
"""Builds the upload-ready asset zips for the GitHub release  mutaharstudio/gaminode-engine  tag  assets-v1.

  python tools/build_release.py --kenney DIR --kaykit DIR --gameicons DIR [--extra DIR] --out DIR

  --kenney    full checkout of github.com/ETdoFresh/kenney.nl   (one zip per pack folder)
  --kaykit    folder holding KayKit-*-1.0 checkouts (github.com/KayKit-Game-Assets)   (one zip per repo)
  --gameicons checkout of github.com/game-icons/icons   (one zip, CC-BY 3.0 -> credits)
  --extra     folder from tools/fetch_extra_sources.py (Poly Haven, ambientCG, + hand-added Quaternius/OGA/itch CC0 packs):
              each subfolder has LICENSE.txt + source.json

Only licenses that allow redistribution: CC0 (Kenney, KayKit, Poly Haven, ambientCG, Quaternius) and CC-BY 3.0 (game-icons.net,
author credit required). A pack without a license file that says so is skipped and listed in the report.
Writes into --out:  lego-<id>.zip ...,  lego-manifest.json (pack -> zip, bytes, sha256, license, author, source),
                    CREDITS.txt (every source + every CC-BY author),  UPLOAD.txt (what to upload, gh command).
Every zip name starts with "lego-" so nothing clashes with files already on the assets-v1 release.
"""
import argparse, hashlib, json, os, re, sys, zipfile

KEEP = {".png", ".jpg", ".jpeg", ".ogg", ".wav", ".mp3", ".ttf", ".otf", ".fnt", ".glb", ".gltf", ".bin", ".xml", ".json", ".txt", ".svg", ".hdr", ".exr"}
DROP_3D = {".obj", ".mtl", ".fbx", ".stl", ".dae", ".blend", ".blend1", ".swf", ".ai", ".psd", ".url", ".unitypackage", ".zip", ".tscn", ".import", ".tres"}
NO_STORE_COMPRESS = {".png", ".jpg", ".jpeg", ".ogg", ".mp3", ".glb"}       # already compressed: store
CC0_WORDS = re.compile(r"CC0|creative\s*commons\s*zero|publicdomain/zero|public domain", re.I)
SKIP_KENNEY = {}   # filled from the license check (packs with no clear redistribution license)

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def license_text(folder, depth=3):
    for dp, dns, fns in os.walk(folder):
        if dp[len(folder):].count(os.sep) >= depth:
            dns[:] = []
        for fn in fns:
            if "licen" in fn.lower():
                try:
                    return open(os.path.join(dp, fn), encoding="utf-8", errors="ignore").read()
                except OSError:
                    pass
    return ""

def pack_files(folder, svg_ok):
    """Files worth shipping. 3D: .glb wins over .gltf of the same model; obj/fbx/stl/dae dropped."""
    files = []
    for dp, dns, fns in os.walk(folder):
        dns[:] = [d for d in dns if d != ".git" and not d.startswith(".")]
        for fn in fns:
            ext = os.path.splitext(fn)[1].lower()
            if ext in DROP_3D or ext not in KEEP:
                continue
            if ext == ".svg" and not svg_ok:
                continue          # Kenney's big vector sheets: the PNGs are already there
            files.append(os.path.join(dp, fn))
    have_glb = {os.path.splitext(f)[0].lower() for f in files if f.lower().endswith(".glb")}
    out = []
    for f in files:
        if f.lower().endswith(".gltf") and os.path.splitext(f)[0].lower() in have_glb:
            continue
        out.append(f)
    return sorted(out)

def write_zip(path, root, files, extra=None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in files:
            rel = os.path.relpath(f, root).replace(os.sep, "/")
            ext = os.path.splitext(f)[1].lower()
            z.write(f, rel, compress_type=zipfile.ZIP_STORED if ext in NO_STORE_COMPRESS else zipfile.ZIP_DEFLATED)
        for name, text in (extra or {}).items():
            z.writestr(name, text)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kenney"); ap.add_argument("--kaykit"); ap.add_argument("--gameicons"); ap.add_argument("--extra")
    ap.add_argument("--out", required=True)
    ap.add_argument("--release-json", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lego", "release.json"))
    ap.add_argument("--only", default="")          # comma list of zip ids (for quick tests)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    only = set(x for x in a.only.split(",") if x)
    man = {"release": "https://github.com/mutaharstudio/gaminode-engine/releases/download/assets-v1/", "packs": {}, "skipped": {}}
    credits_cc0, credits_by = [], {}

    def add(pid, root, files, lic, author, source, extra_files=None, by_authors=None):
        if only and pid not in only:
            return
        if not any(os.path.splitext(f)[1].lower() not in (".txt", ".json", ".xml") for f in files):
            man["skipped"][pid] = "no usable files (download failed or empty)"
            return
        zname = "lego-%s.zip" % pid
        zpath = os.path.join(a.out, zname)
        write_zip(zpath, root, files, extra_files)
        man["packs"][pid] = {"zip": zname, "bytes": os.path.getsize(zpath), "sha256": sha256(zpath), "files": len(files),
                             "license": lic, "author": author, "source": source}
        if by_authors:
            man["packs"][pid]["authors"] = by_authors
        print("  %-48s %5d files %8.1f MB  %s" % (zname, len(files), os.path.getsize(zpath) / 1e6, lic))

    # ---- Kenney: one zip per pack folder
    if a.kenney:
        print("Kenney (CC0)")
        for d in sorted(os.listdir(a.kenney)):
            full = os.path.join(a.kenney, d)
            if not os.path.isdir(full) or d.startswith("."):
                continue
            lt = license_text(full)
            if not CC0_WORDS.search(lt):
                man["skipped"]["k-" + slug(d)] = "no license file that says CC0 (readme only says 'use in projects') - skipped to be safe"
                continue
            add("k-" + slug(d), full, pack_files(full, False), "CC0-1.0", "Kenney (www.kenney.nl)",
                "https://github.com/ETdoFresh/kenney.nl/tree/HEAD/" + d)
        credits_cc0.append("Kenney (www.kenney.nl) - CC0 1.0 - game art, UI, fonts and sounds")
    # ---- KayKit: one zip per repo
    if a.kaykit:
        print("KayKit (CC0)")
        for d in sorted(os.listdir(a.kaykit)):
            full = os.path.join(a.kaykit, d)
            if not os.path.isdir(full):
                continue
            lt = license_text(full)
            if not CC0_WORDS.search(lt):
                man["skipped"]["kk-" + slug(d)] = "license not CC0"
                continue
            add("kk-" + slug(d.replace("KayKit-", "").replace("-1.0", "")), full, pack_files(full, False), "CC0-1.0",
                "Kay Lousberg (www.kaylousberg.com)", "https://github.com/KayKit-Game-Assets/" + d)
        credits_cc0.append("KayKit by Kay Lousberg (www.kaylousberg.com) - CC0 1.0 - 3D models")
    # ---- game-icons.net: CC-BY 3.0 (some authors CC0) -> credits per author
    if a.gameicons:
        print("game-icons.net (CC-BY 3.0)")
        lt = open(os.path.join(a.gameicons, "license.txt"), encoding="utf-8").read()
        cc0_authors = {slug(m.group(1)) for m in re.finditer(r"^- ([^,\n]+?)(?:,[^\n]*)? - CC0\s*$", lt, re.M)}
        files, authors = [], {}
        for d in sorted(os.listdir(a.gameicons)):
            full = os.path.join(a.gameicons, d)
            if not os.path.isdir(full) or d.startswith("."):
                continue
            fs = [f for f in pack_files(full, True) if f.endswith(".svg")]
            if fs:
                files += fs
                authors[d] = {"icons": len(fs), "license": "CC0-1.0" if slug(d) in cc0_authors else "CC-BY-3.0"}
        add("gameicons", a.gameicons, files, "CC-BY-3.0", "game-icons.net contributors", "https://github.com/game-icons/icons",
            {"license.txt": lt}, authors)
        for d, info in sorted(authors.items()):
            if info["license"] == "CC-BY-3.0":
                credits_by[d] = "Icons made by %s (game-icons.net), CC BY 3.0 - https://creativecommons.org/licenses/by/3.0/" % d
    # ---- extra packs (Poly Haven, ambientCG, Quaternius, OpenGameArt/itch CC0 ...)
    if a.extra and os.path.isdir(a.extra):
        print("Extra packs")
        for d in sorted(os.listdir(a.extra)):
            full = os.path.join(a.extra, d)
            src_json = os.path.join(full, "source.json")
            if not os.path.isfile(src_json):
                if os.path.isdir(full):
                    man["skipped"][d] = "no source.json - no LICENSE file that says CC0"
                continue
            info = json.load(open(src_json, encoding="utf-8"))
            lic = info.get("license", "")
            if lic not in ("CC0-1.0", "CC-BY-3.0", "CC-BY-4.0"):
                man["skipped"][d] = "license %r not allowed" % lic
                continue
            add(slug(d), full, pack_files(full, True), lic, info.get("author", ""), info.get("url", ""))
            line = "%s - %s - %s" % (info.get("author", d), lic, info.get("url", ""))
            if slug(d) not in man["packs"]:
                continue                      # nothing shipped -> no credit line
            if lic == "CC0-1.0":
                if line not in credits_cc0:
                    credits_cc0.append(line)
            else:
                credits_by[d] = line

    # ---- manifest, credits, upload notes
    json.dump(man, open(os.path.join(a.out, "lego-manifest.json"), "w"), indent=1)
    # small map for the game (lego/release.json): which zip holds a file
    #   kenney: first folder of the path -> zip      other sources: repo url -> zip (path inside = same path)
    rel = {"base": man["release"], "kenney": {}, "by_url": {}}
    for pid, p in man["packs"].items():
        src = p["source"]
        if "ETdoFresh/kenney.nl/tree/HEAD/" in src:
            rel["kenney"][src.split("/tree/HEAD/")[1]] = p["zip"]
        else:
            rel["by_url"][src] = p["zip"]
    if a.release_json:
        if only and os.path.isfile(a.release_json):          # partial build: keep the other packs
            old = json.load(open(a.release_json))
            for k in ("kenney", "by_url"):
                old.get(k, {}).update(rel[k]); rel[k] = old.get(k, rel[k])
        json.dump(rel, open(a.release_json, "w"), indent=0, sort_keys=True)
    cr = "Gaminode games use free art and sound from these creators. Thank you!\n\n"
    cr += "== CC0 (public domain, no credit required - credited anyway) ==\n" + "\n".join("- " + c for c in credits_cc0) + "\n"
    if credits_by:
        cr += "\n== CC BY (credit required) ==\n" + "\n".join("- " + c for c in credits_by.values()) + "\n"
    open(os.path.join(a.out, "CREDITS.txt"), "w", encoding="utf-8").write(cr)
    total = sum(p["bytes"] for p in man["packs"].values())
    up = ("Upload everything in this folder to the release:\n"
          "  gh release upload assets-v1 lego-*.zip lego-manifest.json CREDITS.txt --repo mutaharstudio/gaminode-engine --clobber\n"
          "(or run tools\\upload_release.bat)\n\n%d zips, %.1f MB total. Skipped packs: %d (see lego-manifest.json \"skipped\").\n"
          % (len(man["packs"]), total / 1e6, len(man["skipped"])))
    open(os.path.join(a.out, "UPLOAD.txt"), "w").write(up)
    print(up)

main()
