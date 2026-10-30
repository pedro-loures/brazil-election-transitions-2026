"""Package the already-computed snapshot and static site for GitHub Pages.

Raw archives and credentials are never included. GitHub Pages serves docs/.
"""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    site=ROOT/"results/2026/flowcharts"
    if not (site/"data/maps/manifest.json").is_file():
        raise SystemExit("Build the flow explorer and map data before preparing publication.")
    docs=ROOT/"docs"
    shutil.copytree(site,docs,dirs_exist_ok=True)
    # Refresh source assets rather than relying on a previously served copy.
    for source in (ROOT/"web/flowcharts").iterdir():
        if source.is_file():shutil.copyfile(source,docs/source.name)
    shutil.copyfile(ROOT/"README.md",docs/"methodology.md")
    (docs/".nojekyll").touch()
    dataset=ROOT/"datasets"
    specifications=[
        (ROOT/"results/2026",dataset/"2026/results",{'.csv','.gz','.json','.png','.pdf'}),
        (ROOT/"data/processed/2026",dataset/"2026/processed",{'.csv','.gz','.json'}),
        (ROOT/"results/twitter_comparison",dataset/"twitter_comparison",{'.csv','.json'}),
    ]
    published=[]
    for source,destination,extensions in specifications:
        if not source.is_dir():continue
        destination.mkdir(parents=True,exist_ok=True)
        for file in sorted(source.iterdir()):
            if file.is_file() and file.suffix in extensions:
                target=destination/file.name;shutil.copyfile(file,target)
                published.append((target,file.relative_to(ROOT).as_posix()))
    provenance=dataset/"2026/provenance";provenance.mkdir(parents=True,exist_ok=True)
    for source,name in [(ROOT/"data/raw/2026/manifest.json","tse-source-manifest.json"),
                        (site/"data/maps/manifest.json","map-source-manifest.json"),
                        (ROOT/"data/raw/geography/tse.json","tse-municipality-crosswalk.json")]:
        target=provenance/name;shutil.copyfile(source,target)
        published.append((target,source.relative_to(ROOT).as_posix()))
    records=[{"path":str(target.relative_to(ROOT)),"restore_path":restore,
              "bytes":target.stat().st_size,"sha256":hashlib.sha256(target.read_bytes()).hexdigest()}
             for target,restore in published]
    manifest={"year":2026,"scope":"Domestic municipality units; overseas voting excluded from analysis",
              "raw_archives_included":False,"files":records}
    (dataset/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    site_bytes=sum(p.stat().st_size for p in docs.rglob('*') if p.is_file())
    print(json.dumps({"site":"docs","site_files":sum(p.is_file() for p in docs.rglob('*')),
                      "site_bytes":site_bytes,"dataset_files":len(records),
                      "dataset_bytes":sum(r["bytes"] for r in records)},indent=2))


if __name__=='__main__':prepare()
