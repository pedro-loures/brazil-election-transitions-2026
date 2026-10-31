"""Population-bin and coordinate-availability audit, not a fitted spatial model."""
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import openpyxl
from elections.hierarchy_inventory import REGIONS,sha256,write_json

RAW=ROOT/'data/raw/spatial_feasibility'
OUT=ROOT/'results/2026/spatial_feasibility'


def population():
    workbook=openpyxl.load_workbook(RAW/'POP2026_20261029.xlsx',read_only=True,data_only=True)
    rows=[]
    for row in workbook['MUNICÍPIOS'].iter_rows(values_only=True):
        if row[0] not in REGIONS or row[1] is None or row[2] is None:continue
        value=re.sub(r'\([^)]*\)','',str(row[4])).strip()
        value=int(float(value)) if isinstance(row[4],(int,float)) else int(value.replace('.','').replace(',',''))
        rows.append({'uf':row[0],'ibge_code':str(int(row[1]))+str(int(row[2])).zfill(5),
                     'population':value,'ibge_name':row[3]})
    result=pd.DataFrame(rows)
    assert not result.ibge_code.duplicated().any()
    assert result.population.gt(0).all()
    return result


def point_inventory():
    columns=['DT_GERACAO','HH_GERACAO','AA_ELEICAO','NR_TURNO','SG_UF','CD_MUNICIPIO',
             'NR_ZONA','NR_SECAO','NR_LOCAL_VOTACAO','NM_LOCAL_VOTACAO','DS_ENDERECO',
             'NR_LATITUDE','NR_LONGITUDE','CD_TIPO_SECAO_AGREGADA','NR_SECAO_PRINCIPAL']
    archive=RAW/'eleitorado_local_votacao_2026.zip'
    with zipfile.ZipFile(archive) as z:
        names=[n for n in z.namelist() if n.upper().endswith('_BRASIL.CSV')]
        assert len(names)==1,names
        with z.open(names[0]) as stream:
            parts=[]
            for chunk in pd.read_csv(stream,sep=';',encoding='latin1',usecols=columns,
                                     dtype={'NR_LATITUDE':str,'NR_LONGITUDE':str},chunksize=150000):
                parts.append(chunk[chunk.SG_UF.ne('ZZ')&chunk.AA_ELEICAO.eq(2026)&chunk.NR_TURNO.isin([1,2])])
    frame=pd.concat(parts,ignore_index=True)
    frame=frame.rename(columns={'SG_UF':'uf','CD_MUNICIPIO':'municipality_code','NR_ZONA':'zone',
                                'NR_SECAO':'section','NR_LOCAL_VOTACAO':'polling_place','NR_TURNO':'round'})
    for source,target in [('NR_LATITUDE','latitude'),('NR_LONGITUDE','longitude')]:
        frame[target]=pd.to_numeric(frame[source].str.replace(',','.',regex=False),errors='coerce')
    frame['coordinate_range_valid']=(frame.latitude.between(-34,6)&frame.longitude.between(-74,-28))
    key=['uf','municipality_code','zone','section','round','polling_place']
    # Never select arbitrarily among conflicting versions of the same section.
    if frame.duplicated(key).any():
        frame.loc[frame.duplicated(key,keep=False)].to_csv(OUT/'conflicting_register_rows.csv.gz',index=False)
        raise ValueError('Duplicate register keys require explicit version handling')
    return frame


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cities=pd.read_csv(ROOT/'results/2026/municipalities.csv')
    config=json.loads((ROOT/'data/raw/geography/tse.json').read_text())
    cross=[]
    for state in config['abr']:
        if state['cd'].upper()=='ZZ':continue
        cross.extend({'uf':state['cd'].upper(),'municipality_code':int(c['cd']),'ibge_code':str(c['cdi'])} for c in state['mu'])
    cities=cities.merge(pd.DataFrame(cross),on=['uf','municipality_code'],how='left',validate='one_to_one')
    cities=cities.merge(population(),on=['uf','ibge_code'],how='left',validate='one_to_one')
    missing=cities[cities.population.isna()]
    missing.to_csv(OUT/'population_unmatched.csv',index=False)
    if len(missing):raise ValueError(f'{len(missing)} municipalities have no official population join')
    edges=np.geomspace(cities.population.min(),cities.population.max(),6)
    # [edge_i,edge_i+1), with the maximum included in the fifth bin.
    cities['population_bin']=np.minimum(np.searchsorted(edges,cities.population,side='right')-1,4)+1
    cities['population_bin']=cities.population_bin.astype(int)
    assert cities.population_bin.between(1,5).all()
    summaries=[]
    for b,block in cities.groupby('population_bin'):
        summaries.append({'bin':int(b),'lower_edge_inclusive':float(edges[b-1]),
                          'upper_edge_exclusive_except_last':float(edges[b]),'municipalities':len(block),
                          'actual_population_min':int(block.population.min()),'actual_population_max':int(block.population.max()),
                          'retained_sections_median':float(block.sections_analyzed.median()),
                          'retained_sections_min':int(block.sections_analyzed.min()),'retained_sections_max':int(block.sections_analyzed.max())})
    cities.to_csv(OUT/'municipality_population_bins.csv',index=False)
    pd.DataFrame(summaries).to_csv(OUT/'population_bin_summary.csv',index=False)
    print(json.dumps(summaries,indent=2),flush=True)
    register=point_inventory()
    write_json(OUT/'register_inventory.json',{'rows':len(register),'rounds':register['round'].value_counts().to_dict(),
               'generation_dates':register[['DT_GERACAO','HH_GERACAO']].drop_duplicates().to_dict('records'),
               'coordinate_range_valid_rows':int(register.coordinate_range_valid.sum()),
               'scope':'Coordinate availability and broad geographic range only. Municipality containment and election-day placement still need validation.'})
    sections=pd.read_csv(ROOT/'results/2026/sections.csv.gz')
    sections=sections[sections.analysis_eligible].copy()
    key=['uf','municipality_code','zone','section']
    points=sections[key+['polling_place_1','eligible_1']].rename(columns={'polling_place_1':'polling_place'})
    for turn in [1,2]:
        local=register[register['round'].eq(turn)][key+['polling_place','latitude','longitude','coordinate_range_valid',
                                                               'NM_LOCAL_VOTACAO','DS_ENDERECO','CD_TIPO_SECAO_AGREGADA','NR_SECAO_PRINCIPAL']]
        points=points.merge(local,on=key+['polling_place'],how='left',validate='one_to_one',suffixes=('',f'_{turn}'))
        if turn==1:
            points=points.rename(columns={c:c+'_1' for c in local.columns if c not in key+['polling_place']})
        else:
            points=points.rename(columns={c:c+'_2' for c in local.columns if c not in key+['polling_place']})
    points['coordinates_available_both_rounds']=points.coordinate_range_valid_1.eq(True)&points.coordinate_range_valid_2.eq(True)
    points['coordinates_stable_approx_10m']=(points.coordinates_available_both_rounds&
          (points.latitude_1-points.latitude_2).abs().le(.0001)&(points.longitude_1-points.longitude_2).abs().le(.0001))
    points=points.merge(cities[['uf','municipality_code','ibge_code','population','population_bin']],on=['uf','municipality_code'],validate='many_to_one')
    # A consistency check against the existing simplified mesh, not independent
    # verification of the school/building or a test of election-day placement.
    from matplotlib.path import Path as PolygonPath
    mesh=json.loads((ROOT/'docs/data/maps/municipality.geojson').read_text())
    shapes={int(f['properties']['key']):f['geometry'] for f in mesh['features']}
    points['inside_simplified_municipality_mesh']=pd.Series(pd.NA,index=points.index,dtype='boolean')
    valid=points[points.coordinates_available_both_rounds]
    for code,block in valid.groupby('municipality_code'):
        geometry=shapes[int(code)]
        polygons=[geometry['coordinates']] if geometry['type']=='Polygon' else geometry['coordinates']
        coordinates=block[['longitude_1','latitude_1']].to_numpy()
        inside=np.zeros(len(block),dtype=bool)
        for polygon in polygons:
            within=PolygonPath(polygon[0]).contains_points(coordinates)
            for hole in polygon[1:]:within &= ~PolygonPath(hole).contains_points(coordinates)
            inside |= within
        points.loc[block.index,'inside_simplified_municipality_mesh']=inside
    points.to_csv(OUT/'section_coordinate_candidates.csv.gz',index=False)
    geos=[]
    for b,block in points.groupby('population_bin'):
        geos.append({'bin':int(b),'retained_sections':len(block),'retained_electorate':int(block.eligible_1.sum()),
                     'coordinate_rows_both_rounds':int(block.coordinates_available_both_rounds.sum()),
                     'coordinate_rows_stable':int(block.coordinates_stable_approx_10m.sum()),
                     'coordinate_availability_fraction':float(block.coordinates_available_both_rounds.mean()),
                     'stable_coordinate_fraction':float(block.coordinates_stable_approx_10m.mean()),
                     'inside_simplified_mesh':int(block.inside_simplified_municipality_mesh.eq(True).sum()),
                     'outside_simplified_mesh_review':int(block.inside_simplified_municipality_mesh.eq(False).sum())})
    pd.DataFrame(geos).to_csv(OUT/'coordinate_coverage_by_bin.csv',index=False)
    write_json(OUT/'audit.json',{'scope':'Feasibility audit; no threshold calibration, spatial grouping, or new transition fitting performed.',
             'population_reference_date':'2026-07-01','population_snapshot':'POP2026_20261029.xlsx',
             'bins':'Five equal-width intervals in log(population); NOT quantiles.',
             'population_bin_edges':edges.tolist(),'bin_summary':summaries,'geolocation_by_bin':geos,
             'geolocation_validation':'Candidates: administrative join, coordinate ranges and simplified-mesh containment check. Outside-mesh sites require review, not automatic deletion; physical-building and election-day relocation validation remain outstanding.',
             'input_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in [RAW/'manifest.json',ROOT/'results/2026/sections.csv.gz',ROOT/'results/2026/municipalities.csv']}})
    print(json.dumps(geos,indent=2),flush=True)


if __name__=='__main__':main()
