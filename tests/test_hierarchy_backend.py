"""Optional backend regression: two cities can share P while differing in S."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/elections-matplotlib')
import importlib.util
import subprocess
import sys
import pytest

pytestmark=pytest.mark.skipif(importlib.util.find_spec('numpyro') is None,reason='Optional NumPyro environment')


def test_vectorized_sampler_cache_is_scoped_to_observation_shape():
    # Isolate the multithreaded JAX runtime from tests of the baseline's process
    # pool; initializing JAX and then forking that same process is unsafe.
    code='''
import numpy as np
from elections.hierarchy import _backend,_sampler
jax,_=_backend()
import jax.numpy as jnp
samplers=[]
for sections in [6,8]:
    sampler=_sampler(sections,2,2.,.5,2,10,10,.8,5,False)
    samplers.append(sampler)
    x=np.ones((sections,5))*20
    y=np.ones((sections,4))*25
    sampler.run(jax.random.PRNGKey(sections),x=jnp.asarray(x),y=jnp.asarray(y),
                place=jnp.asarray(np.arange(sections)%2))
    assert sampler.get_samples()['mu'].shape==(20,5,3)
assert samplers[0] is not samplers[1]
'''
    subprocess.run([sys.executable,'-c',code],check=True,capture_output=True,text=True,timeout=90)
