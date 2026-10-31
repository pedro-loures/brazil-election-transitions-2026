import numpy as np
import pytest
from scripts.build_national_site import compact_city


def record(status='ok'):
    matrix=np.array([[8,1,.5,.5]]*5)
    return {'municipality_code':1,'municipality':'Example','uf':'SC','status':status,'electorate':50,
        'origins':[10]*5,'matrix':matrix.tolist(),'low':(matrix*.5).tolist(),
        'high':np.minimum(matrix*1.2,10).tolist(),'diagnostics':{'status':status}}


def test_publication_retains_expected_margins_and_distinguishes_observed_totals():
    r=record();r['observed_destinations']=[30,10,5,5]
    c=compact_city(r)
    assert np.allclose(np.sum(c['matrix'],axis=1),c['origins'])
    assert not np.allclose(np.sum(c['matrix'],axis=0),c['observed_destinations'])
    assert c['independent_validation_complete'] is False


def test_warning_intervals_are_explicitly_provisional():
    c=compact_city(record('diagnostic_warning'))
    assert 'Provisional' in c['interval_type']
    assert c['matrix'] is not None


def test_missing_new_model_is_not_filled_with_baseline():
    r={'municipality_code':1,'status':'resource_timeout','baseline_matrix':record()['matrix']}
    c=compact_city(r)
    assert c['matrix'] is None and c['low'] is None and c['high'] is None


@pytest.mark.parametrize('bad',[float('nan'),-1.])
def test_invalid_national_flows_cannot_be_published(bad):
    r=record();r['matrix'][0][0]=bad
    with pytest.raises(ValueError):compact_city(r)


def test_intervals_cannot_exceed_their_origin_group():
    r=record();r['high'][0][0]=11
    with pytest.raises(ValueError):compact_city(r)
