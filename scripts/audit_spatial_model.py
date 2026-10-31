"""Audit the extension's exact small-count margins, moments and priors."""
from itertools import product
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.special import gammaln,softmax
from scipy.stats import multivariate_normal
from elections.spatial import OUT
from elections.spatial_model import margin_moments,VARIANTS
from elections.hierarchy import likelihood_audit
from elections.spatial_runner import save


def compositions(n):
    for a in range(n+1):
        for b in range(n-a+1):
            for c in range(n-a-b+1):yield np.array([a,b,c,n-a-b-c])


def exact_dm(x,p,rho):
    states={(0,0,0):1.}
    for n,row in zip(x,p):
        probabilities=[]
        for counts in compositions(int(n)):
            log=gammaln(n+1)-gammaln(counts+1).sum()
            if rho:
                concentration=1/rho-1;alpha=row*concentration
                log+=gammaln(concentration)-gammaln(concentration+n)+(gammaln(alpha+counts)-gammaln(alpha)).sum()
            else:log+=(counts*np.log(row)).sum()
            probabilities.append((counts[:3],np.exp(log)))
        updated={}
        for key,mass in states.items():
            for counts,prob in probabilities:
                dest=tuple(np.array(key)+counts)
                updated[dest]=updated.get(dest,0.)+mass*prob
        states=updated
    return states


def audit(output=OUT):
    output=Path(output);rows=[]
    x=np.array([2,2,1,1,2]);p=np.array([[.8,.08,.04,.08],[.08,.8,.04,.08],[.4,.35,.1,.15],[.3,.25,.25,.2],[.2,.15,.05,.6]])
    for rho in [0,.01,.05,.1]:
        pmf=exact_dm(x,p,rho);support=np.array(list(pmf));mass=np.array(list(pmf.values()))
        mean,cov=margin_moments(x[None],p[None],rho);center=support-mean[0]
        approx=multivariate_normal.pdf(support,mean=mean[0],cov=cov[0]);approx/=approx.sum()
        rows.append({'rho':rho,'N':int(x.sum()),'probability_sum':float(mass.sum()),
            'mean_max_error':float(abs((support*mass[:,None]).sum(0)-mean[0]).max()),
            'covariance_max_error':float(abs(np.einsum('n,ni,nj->ij',mass,center,center)-cov[0]).max()),
            'normalized_normal_grid_TV':float(abs(approx-mass).sum()/2)})
    save(output/'likelihood_audit.json',{'base_model':likelihood_audit(),'extension_exact_dm':rows,
        'scope':'Exact N=8 moment and margin checks; normalized grid comparison differs from fitted continuous density. Does not certify full-size posterior approximation.'})
    rng=np.random.default_rng(20261030);prior={}
    for name,(mu_sd,tau_scale,beta_sd,rho_beta) in VARIANTS.items():
        mu=rng.normal(0,mu_sd,(2000,5,3));tau=abs(rng.normal(0,tau_scale,(2000,1,1)))
        z=rng.normal(size=mu.shape);logits=mu+tau*z
        p=softmax(np.concatenate([logits,np.zeros((2000,5,1))],axis=-1),axis=-1)
        rho=rng.beta(1,rho_beta,2000)
        prior[name]={'probability_below_1pct_fraction':float((p<.01).mean()),
            'probability_above_99pct_fraction':float((p>.99).mean()),'rho_quantiles':np.quantile(rho,[.025,.5,.975]).tolist(),
            'beta_sd':beta_sd,'scope':'Context centered at municipal mean; context effects widen these priors at extreme compositions.'}
    save(output/'prior_predictive.json',prior)
    from elections.hierarchy import validate_counts
    changed=np.array([[3.,2.,1.,3.]])
    rejected=False
    try:validate_counts(x[None],changed,np.array([0]))
    except ValueError:rejected=True
    save(output/'turnover_check.json',{'unequal_population_rejected':rejected,
        'equal_size_membership_turnover_identifiable':False,
        'equal_count_turnover_sensitivity':[{'turnover_fraction':v,'first_electorate':1000,
            'second_electorate':1000,'people_present_both_rounds':int(1000*(1-v)),
            'departures':int(1000*v),'new_registrants':int(1000*v),
            'aggregate_population_check_detects_change':False,
            'full_1000_person_closed_transition_table_exists':False} for v in [.01,.05,.10]],
        'scope':'The paired electorate is a closure assumption. Anonymous aggregate margins cannot identify replacement of voters that preserves category totals.'})
    return rows


if __name__=='__main__':print(audit())
