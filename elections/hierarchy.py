"""Joint municipal/place ecological model, with an explicit approximate likelihood.

The observations are column margins, never observed individual transitions.
NumPyro/ArviZ are optional dependencies (requirements-hierarchy.txt).
"""
from functools import lru_cache, partial
import os
import time

import numpy as np
from scipy.special import softmax
from scipy.stats import binom, norm, multivariate_normal


def validate_counts(x, y, place):
    x, y, place = np.asarray(x, float), np.asarray(y, float), np.asarray(place, int)
    if x.ndim != 2 or x.shape[1] != 5 or y.shape != (len(x), 4) or place.shape != (len(x),):
        raise ValueError("Expected n x 5 origins, n x 4 destinations and n place labels")
    if not np.isfinite(x).all() or not np.isfinite(y).all() or (x < 0).any() or (y < 0).any():
        raise ValueError("Counts must be finite and nonnegative")
    if not np.allclose(x.sum(1), y.sum(1), rtol=0, atol=1e-8) or (x.sum(1) <= 0).any():
        raise ValueError("Transition analysis requires equal positive section electorates")
    if not np.array_equal(np.unique(place), np.arange(place.max()+1)):
        raise ValueError("Place labels must be contiguous starting at zero")
    return x, y, place


def column_moments(x, p):
    """Exact first three-column mean/covariance under independent multinomial rows."""
    x, p = np.asarray(x), np.asarray(p)
    q = p[..., :3]
    mean = np.einsum("...g,...gk->...k", x, q)
    covariance = np.eye(3)*mean[..., None, :] - np.einsum("...g,...gi,...gj->...ij", x, q, q)
    return mean, covariance


def expected_flows(x, place, probabilities):
    """Each draw: sum local expected counts. Preserve the common electorate."""
    counts = np.zeros((probabilities.shape[-3], 5))
    np.add.at(counts, place, x)
    local = probabilities * counts[None, :, :, None]
    return local, local.sum(axis=1)


def exact_margin_pmf(x, p):
    """Small-case reference only: convolve individual categorical trials in 3D.

    Last column is implied by N. This enumerates margin support, not latent tables.
    Deliberately guarded to prevent accidental national-size enumeration.
    """
    x = np.asarray(x, int)
    if x.sum() > 25 or len(x) != len(p) or (x < 0).any():
        raise ValueError("Exact reference restricted to N <= 25")
    states = {(0, 0, 0): 1.}
    for n, row in zip(x, p):
        for _ in range(n):
            new = {}
            for key, probability in states.items():
                for k, prob in enumerate(row):
                    dest = tuple(v+int(k == j) for j, v in enumerate(key))
                    new[dest] = new.get(dest, 0.)+probability*prob
            states = new
    return states


def likelihood_audit():
    """Exact 4-column moments/support and exact binary projection probabilities."""
    p = np.array([[.80,.08,.04,.08],[.08,.80,.04,.08],[.40,.35,.10,.15],
                  [.30,.25,.25,.20],[.20,.15,.05,.60]])
    rows = []
    for counts in [[2,2,1,1,2], [5,5,2,2,6]]:
        x = np.array(counts)
        pmf = exact_margin_pmf(x,p)
        support, mass = np.array(list(pmf)), np.array(list(pmf.values()))
        mean, covariance = column_moments(x,p)
        approx = multivariate_normal.pdf(support, mean=mean, cov=covariance)
        approx /= approx.sum()  # Comparison conditional on valid support, not the fitted likelihood.
        centered = support-mean
        rows.append({"kind":"exact_four_destination", "N":int(x.sum()),
                     "probability_sum":float(mass.sum()),
                     "mean_max_error":float(abs((support*mass[:,None]).sum(0)-mean).max()),
                     "covariance_max_error":float(abs(np.einsum('n,ni,nj->ij',mass,centered,centered)-covariance).max()),
                     "normalized_grid_total_variation":float(abs(approx-mass).sum()/2)})
    for n in [20,100,300,600]:
        x = np.array([n//3,n//3,n//15,n//15, n-2*(n//3)-2*(n//15)])
        for label, probability in [("interior",p[:,0]), ("rare_destination",p[:,2])]:
            pmf = np.array([1.])
            for count, prob in zip(x, probability):
                pmf = np.convolve(pmf, binom.pmf(np.arange(count+1),count,prob))
            mean = x@probability
            sd = np.sqrt(x@(probability*(1-probability)))
            grid = np.arange(n+1)
            approx = norm.cdf((grid+.5-mean)/sd)-norm.cdf((grid-.5-mean)/sd)
            rows.append({"kind":"exact_binary_projection_"+label, "N":n,
                         "total_variation_continuity_corrected":float(abs(approx-pmf).sum()/2),
                         "normal_outside_support_probability":float(1-approx.sum())})
    return rows


def _backend():
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/elections-matplotlib")
    os.environ.setdefault("JAX_PLATFORMS", "cpu")
    import jax
    import numpyro
    jax.config.update("jax_enable_x64", True)
    numpyro.set_host_device_count(4)
    return jax, numpyro


def _model(x, y, place, n_places, mu_sd, tau_scale, no_cross=False):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from jax.nn import softmax as jsoftmax

    mu = numpyro.sample("mu", dist.Normal(0., mu_sd).expand((5,3)).to_event(2))
    tau = numpyro.sample("tau", dist.HalfNormal(tau_scale))
    z = numpyro.sample("z", dist.Normal(0.,1.).expand((n_places,5,3)).to_event(3))
    logits = mu[None]+tau*z
    logits = jnp.concatenate([logits, jnp.zeros((n_places,5,1))], axis=-1)
    if no_cross:
        logits = logits.at[:,0,1].set(-jnp.inf).at[:,1,0].set(-jnp.inf)
    p = jsoftmax(logits,axis=-1)[place,:,:3]
    mean = jnp.einsum("sg,sgk->sk",x,p)
    cov = jnp.eye(3)*mean[:,None,:]-jnp.einsum("sg,sgi,sgj->sij",x,p,p)
    cov = cov+jnp.eye(3)*1e-6  # Numerical jitter, not an estimated overdispersion term.
    numpyro.sample("margins", dist.MultivariateNormal(mean,covariance_matrix=cov).to_event(1), obs=y[:,:3])


@lru_cache(maxsize=16)
def _sampler(n_sections, n_places, mu_sd, tau_scale, chains, warmup, samples, target_accept, max_tree_depth, no_cross):
    # NumPyro's vectorized kernel carries shape-specific state. Reuse only for
    # identical observation shapes, not merely the same number of places.
    _, _ = _backend()
    from numpyro.infer import MCMC, NUTS, init_to_median
    model = partial(_model, n_places=n_places, mu_sd=mu_sd, tau_scale=tau_scale, no_cross=no_cross)
    return MCMC(NUTS(model, target_accept_prob=target_accept, max_tree_depth=max_tree_depth,
                     init_strategy=init_to_median(num_samples=10)),
                num_warmup=warmup, num_samples=samples, num_chains=chains,
                chain_method="vectorized", progress_bar=False, jit_model_args=True)


def fit_hierarchy(x, y, place, *, seed=1, mu_sd=2., tau_scale=.5, chains=4,
                  warmup=700, samples=700, target_accept=.95, max_tree_depth=10, no_cross=False):
    x,y,place = validate_counts(x,y,place)
    jax,_ = _backend()
    import arviz as az
    import jax.numpy as jnp
    started = time.monotonic()
    sampler = _sampler(len(x),int(place.max()+1),mu_sd,tau_scale,chains,warmup,samples,target_accept,max_tree_depth,no_cross)
    sampler.run(jax.random.PRNGKey(seed),x=jnp.asarray(x),y=jnp.asarray(y),place=jnp.asarray(place),
                extra_fields=("diverging","num_steps","accept_prob"))
    posterior = {k: np.asarray(v) for k,v in sampler.get_samples(group_by_chain=True).items()}
    extra = {k: np.asarray(v) for k,v in sampler.get_extra_fields(group_by_chain=True).items()}
    logits = posterior["mu"][:,:,None]+posterior["tau"][:,:,None,None,None]*posterior["z"]
    logits = np.concatenate([logits,np.zeros((*logits.shape[:-1],1))],axis=-1)
    if no_cross:
        logits[...,0,1] = -np.inf
        logits[...,1,0] = -np.inf
    probabilities = softmax(logits,axis=-1).reshape(-1,int(place.max()+1),5,4)
    local, municipal = expected_flows(x,place,probabilities)
    # Include expected municipal flows in chain diagnostics, alongside all parameters.
    diagnostic_samples = {**posterior, "municipal_flow":municipal.reshape(chains,samples,5,4)}
    inference = az.from_dict(posterior=diagnostic_samples)
    summary = az.summary(inference,kind="diagnostics",round_to="none")
    rhat = float(summary.r_hat.max())
    bulk, tail = float(summary.ess_bulk.min()),float(summary.ess_tail.min())
    divergences = int(extra["diverging"].sum())
    depth = int((extra["num_steps"] >= 2**max_tree_depth-1).sum())
    diagnostics = {"rhat_max":rhat,"ess_bulk_min":bulk,"ess_tail_min":tail,
                   "divergences":divergences,"tree_depth_saturated":depth,
                   "mean_accept_probability":float(extra["accept_prob"].mean()),
                   "elapsed_seconds":time.monotonic()-started,"chains":chains,"draws_per_chain":samples,
                   "tau_mean":float(posterior["tau"].mean()),
                   "tau_p025":float(np.quantile(posterior["tau"],.025)),
                   "tau_p975":float(np.quantile(posterior["tau"],.975)),
                   "status":"ok" if rhat<=1.01 and min(bulk,tail)>=400 and not divergences and not depth else "diagnostic_warning"}
    return {"probabilities":probabilities,"local_draws":local,"municipal_draws":municipal,
            "posterior":posterior,"diagnostics":diagnostics,"parameter_diagnostics":summary}


def predictive_checks(x,y,place,probabilities,seed):
    """Replicate actual row-multinomial counts, conditional on posterior P draws."""
    rng = np.random.default_rng(seed)
    indices = np.linspace(0,len(probabilities)-1,min(400,len(probabilities))).astype(int)
    p = probabilities[indices][:,place]
    mean = np.einsum("sg,dsgk->dsk",x,p)
    replicated = np.zeros_like(mean)
    for d in range(len(p)):
        for s in range(len(x)):
            for g in range(5):
                replicated[d,s] += rng.multinomial(int(x[s,g]),p[d,s,g])
    lower,upper = np.quantile(replicated,[.025,.975],axis=0)
    residual = mean.mean(axis=0)-y
    observed_discrepancy = ((y[None]-mean)**2/(mean+1)).sum(axis=(1,2))
    replicated_discrepancy = ((replicated-mean)**2/(mean+1)).sum(axis=(1,2))
    return {"rmse_votes":float(np.sqrt(np.mean(residual**2))),
            "max_section_error_votes":float(abs(residual).max()),
            "expected_margin_max_error_votes":float(abs(residual.sum(axis=0)).max()),
            "ppc_cell_interval_fraction":float(((y>=lower)&(y<=upper)).mean()),
            "ppc_discrepancy_probability":float((replicated_discrepancy>=observed_discrepancy).mean()),
            "ppc_note":"In-sample posterior predictive check of margins; not hidden-flow accuracy or validated confidence coverage."}
