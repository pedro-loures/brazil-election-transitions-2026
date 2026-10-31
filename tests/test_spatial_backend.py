"""Check the sampled likelihood against independently verified DM moments."""
import os
import importlib.util
from pathlib import Path
import subprocess
import sys
import pytest

pytestmark=pytest.mark.skipif(importlib.util.find_spec('numpyro') is None,reason='Optional NumPyro environment')


def test_spatial_likelihood_matches_dm_column_moments():
    code='''
import numpy as np
from scipy.special import softmax
from elections.spatial_model import _model, margin_moments, context_design
from elections.hierarchy import _backend
_backend()
import jax.numpy as jnp
from numpyro.handlers import seed,trace
x=np.array([[20,15,4,3,8],[15,22,3,2,8]],float)
y=np.array([[21,17,3,9],[20,18,4,8]],float)
group=np.array([0,0])
for extended,common in [(False,True),(False,False),(True,False)]:
    context=context_design(x)
    t=trace(seed(_model,8)).get_trace(jnp.asarray(x),jnp.asarray(y),jnp.asarray(group),jnp.asarray(context),1,extended,common,2.,.5,.25,19.)
    mu=np.array(t['mu']['value'])
    logits=np.broadcast_to(mu,(2,5,3)).copy()
    if not common:logits+=float(t['tau']['value'])*np.array(t['z']['value'])[group]
    if extended:logits+=np.einsum('sc,cgk->sgk',context,np.array(t['beta']['value']))
    p=softmax(np.concatenate([logits,np.zeros((2,5,1))],axis=-1),axis=-1)
    mean,cov=margin_moments(x,p,float(t['rho']['value']) if extended else 0)
    distribution=t['margins']['fn'].base_dist
    assert np.allclose(distribution.loc,mean)
    assert np.allclose(distribution.covariance_matrix,cov+np.eye(3)*1e-6)
    assert np.isfinite(np.asarray(t['margins']['fn'].log_prob(jnp.asarray(y[:,:3]))))
'''
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],
                          env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr
