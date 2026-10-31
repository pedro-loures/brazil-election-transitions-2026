"""Supplementary raw-register precision audit; never rewrites frozen eligibility."""
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from elections.spatial import OUT,KEY
from elections.spatial_runner import save


def audit(output=OUT):
    output=Path(output)
    archive=ROOT/'data/raw/spatial_feasibility/eleitorado_local_votacao_2026.zip'
    columns=['SG_UF','CD_MUNICIPIO','NR_ZONA','NR_SECAO','NR_TURNO','NR_LOCAL_VOTACAO','NR_LATITUDE','NR_LONGITUDE']
    parts=[]
    with zipfile.ZipFile(archive) as z:
        name=next(n for n in z.namelist() if n.upper().endswith('_BRASIL.CSV'))
        with z.open(name) as f:
            for chunk in pd.read_csv(f,sep=';',encoding='latin1',usecols=columns,
                                     dtype={'NR_LATITUDE':str,'NR_LONGITUDE':str},chunksize=150000):
                parts.append(chunk[chunk.NR_TURNO.eq(1)&chunk.SG_UF.ne('ZZ')])
    source=pd.concat(parts,ignore_index=True).rename(columns={'SG_UF':'uf','CD_MUNICIPIO':'municipality_code',
        'NR_ZONA':'zone','NR_SECAO':'section','NR_LOCAL_VOTACAO':'polling_place'})
    for col in ['NR_LATITUDE','NR_LONGITUDE']:
        # Number of written decimal places is precision, not verified accuracy.
        source[col+'_decimal_places']=source[col].fillna('').str.replace(',','.',regex=False).str.extract(r'\.(\d+)')[0].fillna('').str.len()
    geo=pd.read_csv(output/'section_coordinates.csv.gz',usecols=KEY+['polling_place','population_bin','coordinate_status','administrative_groups_at_coordinate'])
    joined=geo.merge(source,on=KEY+['polling_place'],how='left',validate='one_to_one')
    joined['coarse_precision_flag']=(joined.NR_LATITUDE_decimal_places.lt(4)|joined.NR_LONGITUDE_decimal_places.lt(4))
    joined.to_csv(output/'coordinate_precision.csv.gz',index=False)
    counts=joined.groupby(['population_bin','coordinate_status']).agg(sections=('section','size'),
        coarse_precision=('coarse_precision_flag','sum'),co_located_multiple_administrative_groups=('administrative_groups_at_coordinate',lambda x:int(x.gt(1).sum()))).reset_index()
    counts.to_csv(output/'coordinate_precision_by_bin.csv',index=False)
    result={'sections':len(joined),'coarse_precision_flag':int(joined.coarse_precision_flag.sum()),
        'verified_with_coarse_precision_flag':int((joined.coarse_precision_flag&joined.coordinate_status.eq('verified_register_boundary')).sum()),
        'minimum_written_latitude_decimals':int(joined.NR_LATITUDE_decimal_places.min()),
        'scope':'Written coordinate precision is not physical accuracy. Flags do not rewrite frozen eligibility; assess grouping sensitivity and unresolved field accuracy separately.'}
    save(output/'coordinate_precision_audit.json',result);return result


if __name__=='__main__':print(audit())
