"""Matched municipal/geographic margin models and an explicit robustness arm.

The extension uses section composition effects and independent Dirichlet-
multinomial origin rows. The likelihood remains a moment-matched normal
approximation to the observed column margins, never observed latent votes.
"""
from functools import lru_cache, partial
import time

import numpy as np
from scipy.special import softmax

from .hierarchy import _backend, validate_counts

VARIANTS = {'primary':(2., .5, .25, 19.), 'tighter':(2., .25, .125, 49.),
            'wider':(3., 1., .5, 9.)}


def context_design(x):
    shares = x/x.sum(1, keepdims=True)
    # Four independent shares; fifth is implied. Fixed first-round transform.
    z = shares[:, :4]
    return (z-z.mean(0))/(z.std(0)+1e-6)


def margin_moments(x, p, rho=0.):
    q = p[..., :3]
    mean = np.einsum('sg,sgk->sk', x, q)
    weights = x*(1+(x-1)*rho)
    diag = np.einsum('sg,sgk->sk', weights, q)
    cov = np.eye(3)*diag[:, None, :]-np.einsum('sg,sgi,sgj->sij', weights, q, q)
    return mean, cov


def _model(x, y, group, context, n_groups, extension, common, mu_sd, tau_scale, beta_sd, rho_beta):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from jax.nn import softmax as jsoftmax
    mu = numpyro.sample('mu', dist.Normal(0, mu_sd).expand((5,3)).to_event(2))
    if common:
        logits = jnp.broadcast_to(mu, (len(x), 5, 3))
    else:
        tau = numpyro.sample('tau', dist.HalfNormal(tau_scale))
        z = numpyro.sample('z', dist.Normal(0,1).expand((n_groups,5,3)).to_event(3))
        logits = mu[None]+tau*z[group]
    rho = 0.
    if extension:
        beta = numpyro.sample('beta', dist.Normal(0, beta_sd).expand((4,5,3)).to_event(3))
        logits = logits+jnp.einsum('sc,cgk->sgk', context, beta)
        rho = numpyro.sample('rho', dist.Beta(1., rho_beta))
    p = jsoftmax(jnp.concatenate([logits, jnp.zeros((len(x),5,1))], axis=-1), axis=-1)[:, :, :3]
    mean = jnp.einsum('sg,sgk->sk', x, p)
    w = x*(1+(x-1)*rho)
    diag = jnp.einsum('sg,sgk->sk', w, p)
    cov = jnp.eye(3)*diag[:,None,:]-jnp.einsum('sg,sgi,sgj->sij', w, p, p)
    numpyro.sample('margins', dist.MultivariateNormal(mean, covariance_matrix=cov+jnp.eye(3)*1e-6).to_event(1), obs=y[:,:3])


@lru_cache(maxsize=4)
def sampler(n, groups, extension, common, variant, chains, warmup, samples, acceptance, depth):
    _backend()
    from numpyro.infer import MCMC, NUTS, init_to_median
    mu, tau, beta, rho = VARIANTS[variant]
    model = partial(_model, n_groups=groups, extension=extension, common=common,
                    mu_sd=mu, tau_scale=tau, beta_sd=beta, rho_beta=rho)
    return MCMC(NUTS(model, target_accept_prob=acceptance, max_tree_depth=depth,
                     init_strategy=init_to_median(num_samples=10)), num_warmup=warmup,
                num_samples=samples, num_chains=chains, chain_method='vectorized', progress_bar=False)


def probability_chunks(posterior, x, group, extension=False, common=False, chunk=256):
    """Avoid materializing all draws × metropolitan sections × 20 cells."""
    mu = posterior['mu'].reshape(-1,5,3)
    z = None if common else posterior['z'].reshape(len(mu), -1,5,3)
    tau = None if common else posterior['tau'].reshape(-1,1,1,1)
    beta = posterior['beta'].reshape(-1,4,5,3) if extension else None
    context = context_design(x)
    for start in range(0, len(x), chunk):
        end = min(start+chunk, len(x))
        logits = np.broadcast_to(mu[:,None], (len(mu),end-start,5,3)).copy()
        if not common:
            logits += tau*z[:,group[start:end]]
        if extension:
            logits += np.einsum('sc,dcgk->dsgk', context[start:end], beta)
        p = softmax(np.concatenate([logits,np.zeros((*logits.shape[:-1],1))],axis=-1),axis=-1)
        yield slice(start,end), p


def flow_draws(posterior, x, group, supports, extension=False, common=False):
    count = posterior['mu'].shape[0]*posterior['mu'].shape[1]
    outputs = {name:np.zeros((count,int(labels.max()+1),5,4)) for name, labels in supports.items() if name != 'section'}
    for subset, p in probability_chunks(posterior,x,group,extension,common):
        f = p*x[None,subset,:,None]
        for name, dest in outputs.items():
            labels = supports[name][subset]
            # Sum draws before computing any interval endpoints.
            for label in np.unique(labels):
                dest[:,label] += f[:,labels == label].sum(1)
    return outputs


def fit(x, y, group, *, seed=1, extension=False, common=False, variant='primary',
        chains=4, warmup=700, samples=700, target_accept=.95, depth=10):
    x,y,group = validate_counts(x,y,group)
    jax,_ = _backend()
    import jax.numpy as jnp
    import arviz as az
    started = time.monotonic()
    run = sampler(len(x),int(group.max()+1),extension,common,variant,chains,warmup,samples,target_accept,depth)
    run.run(jax.random.PRNGKey(seed),x=jnp.asarray(x),y=jnp.asarray(y),group=jnp.asarray(group),
            context=jnp.asarray(context_design(x)),extra_fields=('diverging','num_steps'))
    posterior = {k:np.asarray(v) for k,v in run.get_samples(group_by_chain=True).items()}
    extras = {k:np.asarray(v) for k,v in run.get_extra_fields(group_by_chain=True).items()}
    municipal = flow_draws(posterior,x,group,{'municipality':np.zeros(len(x),int)},extension,common)['municipality'][:,0]
    diagnostics = az.summary(az.from_dict(posterior={**posterior,'municipal_flow':municipal.reshape(chains,samples,5,4)}),kind='diagnostics',round_to='none')
    rhat = float(diagnostics.r_hat.max())
    bulk, tail = float(diagnostics.ess_bulk.min()), float(diagnostics.ess_tail.min())
    divergences = int(extras['diverging'].sum())
    saturation = int((extras['num_steps'] >= 2**depth-1).sum())
    result = {'rhat_max':rhat,'ess_bulk_min':bulk,'ess_tail_min':tail,'divergences':divergences,
              'tree_depth_saturated':saturation, 'elapsed_seconds':time.monotonic()-started,
              'chains':chains,'warmup':warmup,'draws':samples,'approximate_likelihood':True,
              'status':'ok' if rhat <= 1.01 and min(bulk,tail) >= 400 and not divergences and not saturation else 'diagnostic_warning'}
    return posterior, result
