import numpy as np
from elections.national_combined import select_attempt,ordered_inventory


def attempt(status,level='primary',available=True):
    r={'level':level,'diagnostics':{'status':status}}
    if available:r['matrix']=np.ones((5,4)).tolist()
    return r


def test_failed_upgrade_preserves_available_primary():
    primary=attempt('diagnostic_warning')
    assert select_attempt(primary,attempt('resource_timeout','long',False)) is primary


def test_converged_attempt_has_priority_over_provisional():
    primary=attempt('ok');long=attempt('diagnostic_warning','long')
    assert select_attempt(primary,long) is primary
    long=attempt('ok','long')
    assert select_attempt(attempt('diagnostic_warning'),long) is long


def test_unavailable_models_stay_unavailable():
    r=select_attempt(attempt('resource_timeout',available=False),attempt('resource_timeout','long',False))
    assert 'matrix' not in r and r['diagnostics']['status']=='resource_timeout'


def test_national_order_is_deterministic_and_covers_every_city_once():
    inventory=[{'municipality_code':c,'population_bin':b,'sections':s}
               for c,b,s in [(7,1,1),(93831,1,16),(8,2,15),(2550,5,3204),(3,1,2)]]
    a=ordered_inventory(inventory);b=ordered_inventory(list(reversed(inventory)))
    assert a==b
    assert len({c['municipality_code'] for c in a})==len(inventory)
    assert a[0]['municipality_code']==93831
