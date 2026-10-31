import hashlib,json,zipfile
from pathlib import Path
import pytest


def test_release_refuses_partial_run_before_any_git_operation(tmp_path,monkeypatch):
    from scripts import release_national as r
    (tmp_path/'execution_state.json').write_text(json.dumps({'status':'running','pending_cities':5,'publication_allowed':False}))
    calls=[];monkeypatch.setattr(r,'command',lambda *args,**kwargs:calls.append(args))
    with pytest.raises(ValueError,match='not complete'):r.release(tmp_path,tmp_path/'checkout',publish=True,wait=False)
    assert not calls
    assert json.loads((tmp_path/'publication_status.json').read_text())['status']=='release_failed'


def test_reproduction_archive_contains_only_declared_processed_inputs(tmp_path,monkeypatch):
    from scripts import release_national as r
    monkeypatch.setattr(r,'ROOT',tmp_path)
    results=tmp_path/'results/2026/national_combined';(results/'inputs').mkdir(parents=True)
    for name in ['inputs/1.npz','manifest.json','verification.json']:(results/name).write_bytes(b'fixture')
    names=['spatial_pooling/manifest.json','spatial_pooling/section_coordinates.csv.gz',
           'spatial_feasibility/municipality_population_bins.csv','model_agreement/manifest.json','model_agreement/decision.json']
    for name in names:
        p=tmp_path/'results/2026'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
    (results/'draws').mkdir();(results/'draws/private.npz').write_bytes(b'not published')
    destination=r.package_inputs(results,tmp_path/'checkout')
    snapshot=json.loads((destination/'snapshot.json').read_text())
    archive=destination/snapshot['archive']
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==snapshot['sha256']
    with zipfile.ZipFile(archive) as z:
        assert any('inputs/1.npz' in n for n in z.namelist())
        assert not any('/draws/' in n or n.startswith('data/raw/') for n in z.namelist())


def test_restore_rejects_archive_path_traversal_before_baseline_restore(tmp_path,monkeypatch):
    from scripts import restore_national_inputs as r
    monkeypatch.setattr(r,'ROOT',tmp_path)
    calls=[];monkeypatch.setattr(r,'restore',lambda:calls.append(True))
    folder=tmp_path/'datasets/2026/national_combined';folder.mkdir(parents=True)
    archive=folder/'input.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside','bad')
    (folder/'snapshot.json').write_text(json.dumps({'archive':'input.zip','sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
    with pytest.raises(ValueError,match='Unsafe'):r.restore_national()
    assert not calls
