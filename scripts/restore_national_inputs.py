"""Restore the public, hash-verified processed inputs for the national model."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.restore_snapshot import restore


def restore_national():
    folder=ROOT/'datasets/2026/national_combined';manifest=json.loads((folder/'snapshot.json').read_text())
    archive=folder/manifest['archive']
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('National snapshot checksum mismatch')
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            target=(ROOT/entry.filename).resolve()
            if not target.is_relative_to(ROOT):raise ValueError('Unsafe archive path')
        restore()
        z.extractall(ROOT)
    print('Restored frozen processed national inputs. No raw archives or posterior draws were included.')


if __name__=='__main__':restore_national()
