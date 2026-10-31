"""Joint two-regime ecological model and matched one-regime comparators.

All four families share composition coefficients, DM moment overdispersion and
the same approximate margin likelihood. Mixture allocations are marginalized
while fitting; conditional allocation draws propagate membership uncertainty.
"""
from functools import partial
import time
import numpy as np
from scipy.special import softmax, logsumexp
from .hierarchy import _backend, validate_counts
from .spatial_model import context_design

FAMILIES = ('municipal', 'geographic', 'behavioural', 'combined')


def model(x, y, group, context, weight, n_groups, geographic, mixture, variant):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from jax.nn import softmax as sm
    from jax.scipy.special import logsumexp as lse
    scales={'primary':(2.,.5,.25,19.), 'tighter':(2.,.25,.125,49.), 'wider':(3.,1.,.5,9.)}
    mu_sd,tau_sd,beta_sd,rho_beta=scales[variant]
    mu=numpyro.sample('mu',dist.Normal(0,mu_sd).expand((5,3)).to_event(2))
    beta=numpyro.sample('beta',dist.Normal(0,beta_sd).expand((4,5,3)).to_event(3))
    rho=numpyro.sample('rho',dist.Beta(1.,rho_beta))
    logits=mu[None]+jnp.einsum('sc,cgk->sgk',context,beta)
    if geographic:
        tau=numpyro.sample('tau',dist.HalfNormal(tau_sd))
        z=numpyro.sample('z',dist.Normal(0,1).expand((n_groups,5,3)).to_event(3))
        logits=logits+tau*z[group]
    if mixture:
        # Label identification only: component 1 has the larger A->A logit.
        # Other 14 contrasts remain unrestricted. Separation can shrink to zero.
        anchor=numpyro.sample('anchor',dist.HalfNormal(tau_sd))
        rest=numpyro.sample('contrast',dist.Normal(0,tau_sd).expand((14,)).to_event(1))
        delta=jnp.concatenate([anchor[None],rest]).reshape(5,3)
        logits=logits[:,None]+jnp.array([-1.,1.])[None,:,None,None]*delta[None,None]
        mix=numpyro.sample('mix_logit',dist.Normal(0,1))
        log_weights=jnp.log(sm(jnp.stack([jnp.array(0.),mix])))
    else:
        logits=logits[:,None]
        log_weights=jnp.zeros(1)
    p=sm(jnp.concatenate([logits,jnp.zeros((*logits.shape[:-1],1))],axis=-1),axis=-1)[...,:3]
    mean=jnp.einsum('sg,scgk->sck',x,p)
    w=x*(1+(x-1)*rho)
    diag=jnp.einsum('sg,scgk->sck',w,p)
    cov=jnp.eye(3)*diag[...,None,:]-jnp.einsum('sg,scgi,scgj->scij',w,p,p)
    ll=dist.MultivariateNormal(mean,covariance_matrix=cov+jnp.eye(3)*1e-6).log_prob(y[:,None,:3])
    numpyro.factor('margin_log_likelihood',jnp.sum(weight*lse(ll+log_weights[None],axis=1)))


def component_probabilities(posterior,x,group,family,context):
    mu=posterior['mu'].reshape(-1,5,3)
    beta=posterior['beta'].reshape(-1,4,5,3)
    logits=mu[:,None]+np.einsum('sc,dcgk->dsgk',context,beta)
    if family in ['geographic','combined']:
        z=posterior['z'].reshape(len(mu),-1,5,3)
        logits+=posterior['tau'].reshape(-1,1,1,1)*z[:,group]
    if family in ['behavioural','combined']:
        delta=np.concatenate([posterior['anchor'].reshape(-1,1),posterior['contrast'].reshape(-1,14)],axis=1).reshape(-1,5,3)
        logits=logits[:,:,None]+np.array([-1.,1.])[None,None,:,None,None]*delta[:,None,None]
    else:logits=logits[:,:,None]
    return softmax(np.concatenate([logits,np.zeros((*logits.shape[:-1],1))],axis=-1),axis=-1)


def responsibilities(p,x,y,rho,mix_logit,observed):
    """Posterior component probabilities; omitted bootstrap units use the prior."""
    q=p[...,:3]
    mean=np.einsum('sg,dscgk->dsck',x,q)
    weights=x[None]*(1+(x[None]-1)*rho[:,None,None])
    diag=np.einsum('dsg,dscgk->dsck',weights,q)
    cov=np.eye(3)*diag[...,None,:]-np.einsum('dsg,dscgi,dscgj->dscij',weights,q,q)+np.eye(3)*1e-6
    residual=y[None,:,None,:3]-mean
    sign,logdet=np.linalg.slogdet(cov)
    if (sign<=0).any():raise ValueError('Non-positive margin covariance')
    ll=-.5*(3*np.log(2*np.pi)+logdet+np.einsum('dsci,dsci->dsc',residual,np.linalg.solve(cov,residual[...,None])[...,0]))
    log_prior=np.stack([np.zeros_like(mix_logit),mix_logit],axis=-1)
    log_prior-=logsumexp(log_prior,axis=-1,keepdims=True)
    return softmax(log_prior[:,None]+ll*np.asarray(observed)[None,:,None],axis=-1)


def prediction_chunks(posterior,x,y,group,family,weight,seed,chunk=32):
    context=context_design(x)
    count=posterior['mu'].shape[0]*posterior['mu'].shape[1]
    rng=np.random.default_rng(seed)
    for start in range(0,len(x),chunk):
        sl=slice(start,min(start+chunk,len(x)))
        p=component_probabilities(posterior,x[sl],group[sl],family,context[sl])
        if p.shape[2]==2:
            q=responsibilities(p,x[sl],y[sl],posterior['rho'].reshape(-1),posterior['mix_logit'].reshape(-1),weight[sl]>0)
            labels=(rng.random(q.shape[:2])<q[:,:,1]).astype(int)
            selected=np.take_along_axis(p,labels[:,:,None,None,None],axis=2)[:,:,0]
        else:
            labels=None;q=None;selected=p[:,:,0]
        assert selected.shape==(count,len(x[sl]),5,4)
        yield sl,selected,labels,q


def fit(x,y,group,weight,family,seed=1,variant='primary',chains=4,warmup=700,samples=700,acceptance=.97,depth=11):
    if family not in FAMILIES:raise ValueError(family)
    x,y,group=validate_counts(x,y,group)
    weight=np.asarray(weight,float)
    if weight.shape!=(len(x),) or (weight<0).any() or not weight.sum():raise ValueError('Invalid resampling weights')
    jax,_=_backend()
    import jax.numpy as jnp
    import arviz as az
    from numpyro.infer import MCMC,NUTS,init_to_median
    started=time.monotonic()
    fn=partial(model,n_groups=int(group.max()+1),geographic=family in ['geographic','combined'],
               mixture=family in ['behavioural','combined'],variant=variant)
    sampler=MCMC(NUTS(fn,target_accept_prob=acceptance,max_tree_depth=depth,init_strategy=init_to_median(num_samples=10)),
        num_warmup=warmup,num_samples=samples,num_chains=chains,chain_method='vectorized',progress_bar=False)
    sampler.run(jax.random.PRNGKey(seed),jnp.asarray(x),jnp.asarray(y),jnp.asarray(group),jnp.asarray(context_design(x)),jnp.asarray(weight),
        extra_fields=('diverging','num_steps'))
    posterior={k:np.asarray(v) for k,v in sampler.get_samples(group_by_chain=True).items()}
    extras={k:np.asarray(v) for k,v in sampler.get_extra_fields(group_by_chain=True).items()}
    municipal=np.zeros((chains*samples,5,4))
    for sl,p,_,_ in prediction_chunks(posterior,x,y,group,family,weight,seed+1):municipal+=(x[None,sl,:,None]*p).sum(1)
    # Membership draws are needed for intervals. Their independent categorical
    # noise must not conceal poor mixing in the continuous model parameters.
    diag=az.summary(az.from_dict(posterior={**posterior,'municipal_flow':municipal.reshape(chains,samples,5,4)}),kind='diagnostics',round_to='none')
    rhat=float(diag.r_hat.max());bulk=float(diag.ess_bulk.min());tail=float(diag.ess_tail.min())
    divergent=int(extras['diverging'].sum());saturated=int((extras['num_steps']>=2**depth-1).sum())
    return posterior,{'status':'ok' if rhat<=1.01 and min(bulk,tail)>=400 and divergent==0 and saturated==0 else 'diagnostic_warning',
        'rhat_max':rhat,'ess_bulk_min':bulk,'ess_tail_min':tail,'divergences':divergent,'tree_depth_saturated':saturated,
        'elapsed_seconds':time.monotonic()-started,'chains':chains,'warmup':warmup,'draws':samples,
        'approximate_likelihood':True,'membership_uncertainty_included':family in ['behavioural','combined']}
