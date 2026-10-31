"""Outcome-blind geography, information inventory and deterministic pooling."""
from pathlib import Path
import hashlib
import io
import json
import unicodedata
import zipfile

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .hierarchy_inventory import ROOT, REGIONS, sha256, write_json
from .model import ORIGINS

OUT = ROOT / 'results/2026/spatial_pooling'
RAW = ROOT / 'data/raw/spatial_pooling'
AUDIT = ROOT / 'results/2026/spatial_feasibility'
KEY = ['uf', 'municipality_code', 'zone', 'section']
TARGETS = [5, 10, 20, 40, 80, 160]
DIAMETERS = [1, 5, 20, 50]
EARTH_KM = 6371.0088


def distances(a, b):
    """Great-circle km; input last dimension is latitude, longitude degrees."""
    a, b = np.radians(a), np.radians(b)
    delta = a-b
    h = np.sin(delta[..., 0]/2)**2 + np.cos(a[..., 0])*np.cos(b[..., 0])*np.sin(delta[..., 1]/2)**2
    return 2*EARTH_KM*np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def diameter(points):
    points = np.asarray(points)
    return float(distances(points[:, None], points[None, :]).max()) if len(points) > 1 else 0.


def neighbour_edges(points, k=8):
    """Symmetrized k-nearest-site graph on the sphere, no dense city matrix."""
    points = np.asarray(points)
    if len(points) < 2:
        return []
    rad = np.radians(points)
    xyz = np.c_[np.cos(rad[:, 0])*np.cos(rad[:, 1]), np.cos(rad[:, 0])*np.sin(rad[:, 1]), np.sin(rad[:, 0])]
    _, near = cKDTree(xyz).query(xyz, k=min(k+1, len(points)))
    pairs = {(min(i, int(j)), max(i, int(j))) for i, row in enumerate(near) for j in row if i != j}
    return sorted((float(distances(points[i], points[j])), i, j) for i, j in pairs)


def partition(points, target, max_diameter, k=8):
    """Keep exact co-locations together. Merge shortest admissible graph edges.

    At least one group must be below target. Diameter is checked on every merge;
    target is a soft size target, never a geographic exception. No outcomes used.
    """
    coords = np.asarray(points, float)
    if coords.ndim != 2 or coords.shape[1] != 2 or not len(coords) or not np.isfinite(coords).all():
        raise ValueError('Finite nonempty n×2 coordinates required')
    if target < 1 or max_diameter <= 0:
        raise ValueError('Positive target and diameter required')
    sites, section_site, weight = np.unique(coords, axis=0, return_inverse=True, return_counts=True)
    parent = np.arange(len(sites))
    members = {i: [i] for i in parent}
    counts = dict(enumerate(weight.tolist()))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return int(i)

    edges = neighbour_edges(sites, k)
    for _, i, j in edges:
        a, b = find(i), find(j)
        if a == b or min(counts[a], counts[b]) >= target:
            continue
        indices = members[a]+members[b]
        if diameter(sites[indices]) > max_diameter+1e-9:
            continue
        a, b = min(a, b), max(a, b)
        parent[b] = a
        members[a] += members.pop(b)
        counts[a] += counts.pop(b)
    roots = np.array([find(i) for i in section_site])
    labels = np.unique(roots, return_inverse=True)[1]
    return labels


def information(x):
    x = np.asarray(x, float)
    shares = x/x.sum(1, keepdims=True)
    rank = int(np.linalg.matrix_rank(shares))
    return {'sections':len(x), 'electorate':int(x.sum()), 'turnout':int(x[:, :4].sum()),
            'design_rank':rank, 'design_condition':float(np.linalg.cond(shares)) if rank == 5 else None,
            'composition_sd':float(shares.std(0).mean()),
            **{f'origin_{g}':int(x[:, i].sum()) for i, g in enumerate(ORIGINS)}}


def group_inventory(x, points, labels, target, cap):
    rows = []
    for label in np.unique(labels):
        mask = labels == label
        coords = np.unique(points[mask], axis=0)
        rows.append({'group':int(label), **information(x[mask]), 'sites':len(coords),
                     'latitude':float(coords[:, 0].mean()), 'longitude':float(coords[:, 1].mean()),
                     'diameter_km':diameter(coords), 'target_sections':target, 'diameter_cap_km':cap,
                     'undersized':bool(mask.sum() < target), 'overshoot_sections':max(0, int(mask.sum())-target),
                     'isolated_below_target':bool(len(coords) == 1 and mask.sum() < target)})
    return rows


def normalize_address(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().upper()
    return ''.join(c for c in s if c.isalnum())


def verify_geography(output=OUT):
    """Detailed IBGE geometry + two-round register checks, not field verification."""
    import shapefile
    from shapely.geometry import shape
    from shapely import covers, points as make_points
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = RAW/'BR_Municipios_2025.zip'
    if not archive.exists():
        part = archive.with_suffix('.zip.part')
        if part.exists() and zipfile.is_zipfile(part):
            part.rename(archive)
        else:
            raise FileNotFoundError('Download the official detailed boundary archive first')
    extraction = RAW/'boundary_2025'
    extraction.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if Path(name).suffix.lower() in ['.shp', '.shx', '.dbf', '.prj']:
                destination = extraction/Path(name).name
                if not destination.exists():
                    with z.open(name) as source, destination.open('wb') as dest:
                        import shutil
                        shutil.copyfileobj(source, dest)
    frame = pd.read_csv(AUDIT/'section_coordinate_candidates.csv.gz')
    if frame.duplicated(KEY).any():
        raise ValueError('Duplicate retained section identifiers')
    frame['address_stable'] = [normalize_address(a) == normalize_address(b) and bool(normalize_address(a))
                               for a, b in zip(frame.DS_ENDERECO_1.fillna(''), frame.DS_ENDERECO_2.fillna(''))]
    frame['aggregation_stable'] = (frame.CD_TIPO_SECAO_AGREGADA_1.fillna(-999).eq(frame.CD_TIPO_SECAO_AGREGADA_2.fillna(-999)) &
                                   frame.NR_SECAO_PRINCIPAL_1.fillna(-999).eq(frame.NR_SECAO_PRINCIPAL_2.fillna(-999)))
    frame['inside_detailed_boundary'] = False
    wanted = {str(k): v.index for k, v in frame.groupby('ibge_code')}
    fields = None
    reader = shapefile.Reader(str(next(extraction.glob('*.shp'))), encoding='utf-8')
    fields = [v[0] for v in reader.fields[1:]]
    code_position = fields.index('CD_MUN')
    matched_codes = set()
    for record in reader.iterShapeRecords():
        code = str(record.record[code_position])
        if code not in wanted:
            continue
        indices = wanted[code]
        valid = frame.loc[indices, 'coordinates_available_both_rounds'].eq(True)
        indices = indices[valid]
        geometry = shape(record.shape.__geo_interface__)
        if not geometry.is_valid:
            from shapely import make_valid
            geometry = make_valid(geometry)
        coordinates = frame.loc[indices, ['longitude_1', 'latitude_1']].to_numpy()
        frame.loc[indices, 'inside_detailed_boundary'] = covers(geometry, make_points(coordinates))
        matched_codes.add(code)
    good = (frame.coordinates_available_both_rounds.eq(True) & frame.coordinates_stable_approx_10m.eq(True) &
            frame.address_stable & frame.aggregation_stable & frame.inside_detailed_boundary)
    frame['coordinate_status'] = np.where(good, 'verified_register_boundary',
        np.where(frame.coordinates_available_both_rounds.eq(True), 'unresolved', 'missing'))
    frame['coordinate_reason'] = np.select([
        ~frame.coordinates_available_both_rounds.eq(True), ~frame.coordinates_stable_approx_10m.eq(True),
        ~frame.address_stable, ~frame.aggregation_stable, ~frame.inside_detailed_boundary],
        ['missing_or_range_invalid', 'coordinate_relocation', 'address_changed_or_missing', 'aggregation_changed',
         'outside_detailed_boundary_or_unmatched_code'], default='register_and_boundary_consistent')
    frame['site_key'] = frame.uf+':'+frame.municipality_code.astype(str)+':'+frame.latitude_1.astype(str)+':'+frame.longitude_1.astype(str)
    admin = frame[['uf','municipality_code','zone','polling_place']].astype(str).agg(':'.join, axis=1)
    frame['administrative_key'] = admin
    reused = frame.groupby('site_key').administrative_key.nunique()
    frame['administrative_groups_at_coordinate'] = frame.site_key.map(reused)
    frame.to_csv(output/'section_coordinates.csv.gz', index=False)
    frame[~good].to_csv(output/'coordinate_exceptions.csv.gz', index=False)
    address_review = frame[frame.inside_simplified_municipality_mesh.eq(False)].copy()
    address_review.to_csv(output/'simplified_boundary_exception_review.csv.gz', index=False)
    coverage = frame.groupby(['population_bin','coordinate_status']).agg(sections=('section','size'),electorate=('eligible_1','sum')).reset_index()
    coverage.to_csv(output/'coordinate_coverage.csv', index=False)
    audit = {'retained_sections':len(frame), 'statuses':frame.coordinate_status.value_counts().to_dict(),
             'simplified_exceptions':len(address_review), 'exceptions_resolved_by_detailed_mesh':int(address_review.coordinate_status.eq('verified_register_boundary').sum()),
             'address_changes_or_missing':int((~frame.address_stable).sum()), 'aggregation_changes':int((~frame.aggregation_stable).sum()),
             'shared_coordinate_admin_groups':int(reused.gt(1).sum()), 'unmatched_ibge_codes':sorted(set(wanted)-matched_codes),
             'boundary_vintage':'2025', 'coordinate_register_vintage':'2026-10-25',
             'verification_scope':'Two-round register/address/aggregation consistency and detailed IBGE containment; not independent field or election-day verification.',
             'boundary_url':'https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2025/Brasil/BR_Municipios_2025.zip',
             'boundary_sha256':sha256(archive)}
    write_json(output/'geography_audit.json', audit)
    return audit


def seed_for(*parts):
    return int.from_bytes(hashlib.sha256(':'.join(map(str, parts)).encode()).digest()[:4], 'big')


def select_sample(inventory, seed=20261030):
    """Region-balanced farthest-first design selection, using only first-round features."""
    rng = np.random.default_rng(seed)
    selected = []
    features = ['sections', 'composition_sd', 'coordinate_coverage', 'median_neighbour_km']+[f'origin_share_{g}' for g in ORIGINS]
    for bin_no in range(1, 6):
        block = inventory[inventory.population_bin.eq(bin_no)].sort_values('municipality_code').copy()
        if bin_no == 5:
            chosen = block.index.tolist()
        else:
            feature = block[features].fillna(0).to_numpy(float)
            feature[:, 0] = np.log1p(feature[:, 0])
            feature = (feature-feature.mean(0))/(feature.std(0)+1e-8)
            selected_positions = []
            region_counts = {r:0 for r in block.region.unique()}
            for _ in range(10):
                available = np.array([i for i in range(len(block)) if i not in selected_positions])
                least = min(region_counts[block.iloc[i].region] for i in available)
                available = np.array([i for i in available if region_counts[block.iloc[i].region] == least])
                if selected_positions:
                    score = ((feature[available, None]-feature[selected_positions][None])**2).sum(2).min(1)
                    pick = int(available[np.argmax(score)])
                else:
                    pick = int(available[int(rng.integers(len(available)))])
                selected_positions.append(pick)
                region_counts[block.iloc[pick].region] += 1
            chosen = block.iloc[selected_positions].index.tolist()
        # Balance the held-out region counts too; no outcomes enter either split.
        validation_count = 3 if bin_no == 5 else 4
        order = rng.permutation(chosen).tolist()
        held = []
        held_regions = set()
        for i in order:
            if block.loc[i, 'region'] not in held_regions:
                held.append(i); held_regions.add(block.loc[i, 'region'])
            if len(held) == validation_count:
                break
        held += [i for i in order if i not in held][:validation_count-len(held)]
        for i in chosen:
            row = block.loc[i].to_dict()
            row['split'] = 'validation' if i in held else 'development'
            selected.append(row)
    return pd.DataFrame(selected)
