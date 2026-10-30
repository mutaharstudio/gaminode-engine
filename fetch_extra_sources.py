#!/usr/bin/env python3
"""Fetches the CC0 sources that have a public API into  <out>/<pack>/  (each with LICENSE.txt + source.json),
ready for  build_release.py --extra <out>.  Runs on GitHub Actions (open internet) or any PC with Python 3.

  python fetch_extra_sources.py --out extra [--poly-textures 40 --poly-hdris 12 --poly-models 20 --ambientcg 40]

  Poly Haven  (api.polyhaven.com)        CC0  - textures (1k JPG: diffuse, normal GL, rough, AO), HDRIs (1k .hdr), models (1k glTF)
  ambientCG   (ambientcg.com/api/v2)      CC0  - materials (1K-JPG)
Not automatic (no API / license can't be checked by a script): Quaternius, OpenGameArt, itch.io.
For those: put a folder  <out>/quaternius-<pack>/  or  oga-<name>/  itch-<name>/  with the files + a LICENSE.txt that says CC0;
this script writes their source.json only when that license text says CC0 (else the folder is skipped by build_release.py).
"""
import argparse, io, json, os, re, sys, time, urllib.request, zipfile

UA = {"User-Agent": "GaminodeAI-asset-fetch/1.0 (github.com/mutaharstudio/gaminode-engine; CC0 packs for game making)"}

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 + 3 * i)

def get_json(url):
    return json.loads(get(url).decode("utf-8"))

def save(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = get(url)
    with open(path, "wb") as f:
        f.write(data)

def source(dirpath, license_, author, url, note):
    os.makedirs(dirpath, exist_ok=True)
    open(os.path.join(dirpath, "LICENSE.txt"), "w").write(note + "\n")
    json.dump({"license": license_, "author": author, "url": url}, open(os.path.join(dirpath, "source.json"), "w"), indent=1)

def polyhaven(out, kind, count):
    d = os.path.join(out, "polyhaven-" + kind)
    source(d, "CC0-1.0", "Poly Haven (polyhaven.com)", "https://polyhaven.com", "Poly Haven assets are CC0 1.0 (https://polyhaven.com/license).")
    assets = get_json("https://api.polyhaven.com/assets?t=" + kind)
    ids = sorted(assets, key=lambda k: -int(assets[k].get("download_count", 0)))[:count]
    ok = 0
    for aid in ids:
        try:
            files = get_json("https://api.polyhaven.com/files/" + aid)
            if kind == "hdris":
                save(files["hdri"]["1k"]["hdr"]["url"], os.path.join(d, aid, aid + "_1k.hdr"))
            elif kind == "textures":
                for m in ("Diffuse", "nor_gl", "Rough", "AO"):
                    if m in files and "1k" in files[m] and "jpg" in files[m]["1k"]:
                        save(files[m]["1k"]["jpg"]["url"], os.path.join(d, aid, "%s_%s_1k.jpg" % (aid, m.lower())))
            else:
                g = files["gltf"]["1k"]["gltf"]
                save(g["url"], os.path.join(d, aid, aid + ".gltf"))
                for rel, inc in g.get("include", {}).items():
                    save(inc["url"], os.path.join(d, aid, rel))
            a = assets[aid]
            json.dump({"id": aid, "name": a.get("name", aid), "tags": a.get("tags", []), "categories": a.get("categories", [])},
                      open(os.path.join(d, aid, "info.json"), "w"))
            ok += 1
        except Exception as e:
            print("  skip polyhaven %s %s: %s" % (kind, aid, e))
    print("polyhaven %s: %d/%d" % (kind, ok, len(ids)))

def ambientcg(out, count):
    d = os.path.join(out, "ambientcg-materials")
    source(d, "CC0-1.0", "ambientCG (ambientcg.com)", "https://ambientcg.com", "ambientCG assets are CC0 1.0 (https://docs.ambientcg.com/license/).")
    lst = get_json("https://ambientcg.com/api/v2/full_json?type=Material&sort=Popular&limit=%d&include=downloadData,tagData" % count)
    ok = 0
    for a in lst.get("foundAssets", []):
        aid = a.get("assetId", "")
        try:
            dls = a["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
            dl = next((x for x in dls if x.get("attribute") == "1K-JPG"), None)
            if not dl:
                continue
            z = zipfile.ZipFile(io.BytesIO(get(dl["downloadLink"])))
            for n in z.namelist():
                if n.lower().endswith((".jpg", ".png")) and "preview" not in n.lower():
                    os.makedirs(os.path.join(d, aid), exist_ok=True)
                    open(os.path.join(d, aid, os.path.basename(n)), "wb").write(z.read(n))
            json.dump({"id": aid, "tags": a.get("tags", [])}, open(os.path.join(d, aid, "info.json"), "w"))
            ok += 1
        except Exception as e:
            print("  skip ambientcg %s: %s" % (aid, e))
    print("ambientcg: %d" % ok)

def manual(out):
    cc0 = re.compile(r"CC0|creative\s*commons\s*zero|publicdomain/zero", re.I)
    for d in sorted(os.listdir(out)):
        full = os.path.join(out, d)
        if not os.path.isdir(full) or not d.startswith(("quaternius-", "oga-", "itch-")):
            continue
        lic = ""
        for dp, _, fns in os.walk(full):
            for fn in fns:
                if "licen" in fn.lower():
                    lic += open(os.path.join(dp, fn), errors="ignore").read()
        if d.startswith("quaternius-") and not lic:
            lic = "Quaternius assets are CC0 1.0 (quaternius.com)."
            open(os.path.join(full, "LICENSE.txt"), "w").write(lic + "\n")
        if cc0.search(lic):
            author = "Quaternius (quaternius.com)" if d.startswith("quaternius-") else d
            json.dump({"license": "CC0-1.0", "author": author, "url": "see LICENSE.txt"}, open(os.path.join(full, "source.json"), "w"))
            print("manual pack ok: " + d)
        else:
            print("manual pack SKIPPED (no CC0 license text): " + d)
            if os.path.exists(os.path.join(full, "source.json")):
                os.remove(os.path.join(full, "source.json"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--poly-textures", type=int, default=40)
    ap.add_argument("--poly-hdris", type=int, default=12)
    ap.add_argument("--poly-models", type=int, default=20)
    ap.add_argument("--ambientcg", type=int, default=40)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for kind, n in (("textures", a.poly_textures), ("hdris", a.poly_hdris), ("models", a.poly_models)):
        if n > 0:
            try:
                polyhaven(a.out, kind, n)
            except Exception as e:
                print("polyhaven %s failed: %s" % (kind, e))
    if a.ambientcg > 0:
        try:
            ambientcg(a.out, a.ambientcg)
        except Exception as e:
            print("ambientcg failed: %s" % e)
    manual(a.out)

main()
