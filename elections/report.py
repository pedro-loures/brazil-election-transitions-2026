"""Offline HTML report and exportable scientific figures."""
import base64
from html import escape
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def write_report(cities, flows, pairs, metadata, output):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for label, color in [("a", "#b91c1c"), ("b", "#1d4ed8")]:
        series = cities[f"corr_{label}_net_new_valid"].dropna()
        axes[0].hist(series, bins=np.linspace(-1, 1, 41), histtype="step", linewidth=2,
                     label=f"Candidate {metadata['finalists'][label]['number']}", color=color)
    axes[0].set(xlabel="Within-municipality section correlation", ylabel="Municipalities",
                title="Vote gains vs net increase in valid votes")
    axes[0].legend()
    axes[1].hist(cities.electorate_coverage.dropna(), bins=np.linspace(0, 1, 41), color="#475569")
    axes[1].set(xlabel="Share of round-1 electorate in analyzed sections", ylabel="Municipalities",
                title="Coverage after section validation")
    fig.savefig(output / "national_overview.png", dpi=180)
    fig.savefig(output / "national_overview.pdf")
    plt.close(fig)
    image = base64.b64encode((output / "national_overview.png").read_bytes()).decode()
    columns = ["uf", "municipality_code", "municipality", "sections_union", "sections_analyzed",
               "sections_excluded", "electorate_coverage", "delta_a", "delta_b", "delta_turnout",
               "delta_invalid", "corr_a_net_new_valid", "corr_b_net_new_valid", "model_status",
               "reference_all_totals_match", "a_mobilization_lower", "a_mobilization_upper",
               "a_lower_if_no_cross", "b_mobilization_lower", "b_mobilization_upper", "b_lower_if_no_cross",
               "proportional_testable_sections", "proportional_infeasible_sections", "no_cross_section_infeasible",
               "full_rmse_votes", "no_cross_rmse_votes", "bootstrap_successful", "bootstrap_requested",
               "design_condition", "design_rank", "bootstrap_status"]
    columns += [f"{c}_{t}" for c in ["a", "b", "other", "turnout", "invalid", "abstention", "eligible"] for t in [1, 2]]
    columns = [c for c in columns if c in cities]
    data = cities[columns].to_json(orient="records", force_ascii=False)
    packed = {}
    if not flows.empty:
        for (uf, code), group in flows.groupby(["uf", "municipality_code"]):
            packed[f"{uf}-{code}"] = json.loads(group[[c for c in ["model", "origin", "destination",
                "estimated_voters", "bootstrap_p025", "bootstrap_p975"] if c in group]].to_json(orient="records"))
    payload = json.dumps({"cities": json.loads(data), "flows": packed}, ensure_ascii=False).replace("<", "\\u003c")
    good = int(cities.model_status.eq("ok").sum())
    summary = {"municipalities": len(cities), "sections_analyzed": int(pairs.analysis_eligible.sum()),
               "sections_union": len(pairs), "successful_full_models": good,
               "reference_mismatch_municipalities": int((~cities.reference_all_totals_match).sum()),
               "bootstrap_draws_per_model": metadata["bootstrap"],
               "candidate_a": metadata["finalists"]["a"], "candidate_b": metadata["finalists"]["b"],
               "totals_domestic": {f"{c}_{t}": int(cities[f"{c}_{t}"].sum())
                                   for c in ["a", "b", "other", "eligible", "turnout", "invalid"] for t in [1, 2]},
               "logs_status": metadata["logs_status"]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    html = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Brazil presidential runoff: municipality analysis</title>
<style>
body{font:16px/1.55 system-ui,sans-serif;margin:32px auto;max-width:1200px;padding:0 20px;color:#172033;background:#fafbfc}
h1{line-height:1.2}h2{margin-top:32px} .note{background:#fff3d6;padding:16px;border-left:4px solid #aa7600}
table{border-collapse:collapse;width:100%;font-size:14px;background:white}td,th{padding:9px;text-align:right;border-bottom:1px solid #ddd}
td:first-child,th:first-child{text-align:left}button,input,select{font:inherit;padding:7px;margin:4px}button{cursor:pointer}
img{width:100%}.scroll{overflow:auto}.cards{display:flex;gap:24px;flex-wrap:wrap}.card{background:#fff;padding:16px;border:1px solid #ddd}
.muted{color:#596577}#table tr[data-index]{cursor:pointer}#table tr[data-index]:hover{background:#eaf1fa}
</style>
<h1>Brazil: presidential runoff analysis, YEAR</h1>
<p>Official TSE bulk data. All domestic municipality units in the presidential files; overseas voting (ZZ) excluded.
Candidate A: NAMEA (NUMBERA). Candidate B: NAMEB (NUMBERB).</p>
<div class="cards"><div class="card"><b>NCITIES</b> municipalities</div><div class="card"><b>NSECTIONS</b> analyzed sections</div>
<div class="card"><b>NMODELS</b> fitted full models</div><div class="card"><b>NDRAWS</b> bootstrap resamples per eligible model</div></div>
<p class="note">Observed totals and accounting identities do not identify individual voter movements. Flow estimates use an explicit common-transition model;
the thread did not specify its original estimator. Correlations share accounting components and do not establish campaign effects.
No fraud classification is produced. Voting-machine event logs have not been loaded; no national timing result is claimed.</p>
<img alt="Histograms of candidate correlations and section coverage" src="data:image/png;base64,FIGURE">
<h2>Municipalities</h2><p>Search by name, UF, or TSE municipality code. Click a row for details.</p>
<input id="search" aria-label="Search municipality" placeholder="Search municipality or UF" size="32">
<select id="sort" aria-label="Sort"><option value="municipality">Name</option><option value="delta_a">Candidate A gain</option>
<option value="delta_b">Candidate B gain</option><option value="electorate_coverage">Coverage</option></select>
<button id="previous">Previous</button><button id="next">Next</button><span id="count"></span>
<div class="scroll"><table id="table"></table></div><div id="detail"></div>
<h2>Files and methodology</h2><p><a href="municipalities.csv">Municipality results CSV</a> · <a href="estimated_flows.csv.gz">Estimated flows CSV.gz</a> ·
<a href="sections.csv.gz">Section diagnostics CSV.gz</a> · <a href="reference_audit.csv">Independent summary reconciliation CSV</a> ·
<a href="national_overview.pdf">Figure PDF</a> · <a href="../../README.md">Methodology and commands</a></p>
<p class="muted">Model: minimize Σ‖xₛP−yₛ‖²/Nₛ with nonnegative row-stochastic transition rates and exact municipal destination margins.
The full model allows all transitions; the sensitivity model prohibits A↔B switching. Section fits can have nonzero residuals.
Bootstrap ranges reflect section resampling under this model, not individual-vote identification or uncertainty in the complete count.</p>
<script type="application/json" id="data">PAYLOAD</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);let page=0,filtered=[];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>x==null?'—':typeof x==='number'?x.toLocaleString('en',{maximumFractionDigits:2}):esc(x);
const table=(headers,rows)=>'<table><thead><tr>'+headers.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(x=>'<td>'+fmt(x)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
function render(){const q=document.querySelector('#search').value.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
const sort=document.querySelector('#sort').value;filtered=D.cities.filter(c=>(c.municipality+' '+c.uf+' '+c.municipality_code).normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().includes(q));
filtered.sort((a,b)=>sort==='municipality'?a.municipality.localeCompare(b.municipality):((b[sort]??-Infinity)-(a[sort]??-Infinity)));
page=Math.min(page,Math.max(0,Math.ceil(filtered.length/50)-1));const shown=filtered.slice(page*50,page*50+50);
document.querySelector('#table').innerHTML='<tr><th>Municipality</th><th>UF</th><th>Gain A</th><th>Gain B</th><th>Coverage</th><th>Model</th></tr>'+shown.map((c,i)=>'<tr data-index="'+(page*50+i)+'"><td>'+esc(c.municipality)+'</td><td>'+esc(c.uf)+'</td><td>'+fmt(c.delta_a)+'</td><td>'+fmt(c.delta_b)+'</td><td>'+fmt(100*c.electorate_coverage)+'%</td><td>'+esc(c.model_status)+'</td></tr>').join('');
document.querySelector('#count').textContent=filtered.length+' municipalities; page '+(page+1);
document.querySelectorAll('[data-index]').forEach(r=>r.onclick=()=>detail(filtered[Number(r.dataset.index)]));}
function detail(c){const names={a:'Candidate A',b:'Candidate B',other:'Other candidates',invalid:'Blank/null',abstention:'Abstention'};
let h='<h2>'+esc(c.municipality)+' · '+esc(c.uf)+' · TSE '+c.municipality_code+'</h2>';
h+=table(['Observed counts','Round 1','Round 2'],['a','b','other','invalid','turnout','abstention','eligible'].map(k=>[names[k]||k,c[k+'_1'],c[k+'_2']]));
h+='<p>Analyzed '+c.sections_analyzed+' of '+c.sections_union+' sections. Coverage '+fmt(c.electorate_coverage*100)+'%. Independent municipal summary matches: '+esc(c.reference_all_totals_match)+'.</p>';
h+='<h3>Gross flows from previous blank/null voters or abstainers: bounds</h3>';
h+=table(['Candidate','Unrestricted lower','Unrestricted upper','Lower if no finalist switching'],['a','b'].map(k=>[names[k],c[k+'_mobilization_lower'],c[k+'_mobilization_upper'],c[k+'_lower_if_no_cross']]));
h+='<p>Bounds cover analyzed sections only. Conditional no-switch bounds apply only under that assumption. Sections incompatible with no switching: '+c.no_cross_section_infeasible+'.</p>';
h+='<p>Section correlations: A '+fmt(c.corr_a_net_new_valid)+'; B '+fmt(c.corr_b_net_new_valid)+'. Proportional-allocation joint assumptions infeasible in '+c.proportional_infeasible_sections+' of '+c.proportional_testable_sections+' testable sections.</p>';
h+='<p>Full model: '+esc(c.model_status)+'; section RMSE '+fmt(c.full_rmse_votes)+' votes. No-switch model RMSE '+fmt(c.no_cross_rmse_votes)+'. Successful resamples '+fmt(c.bootstrap_successful)+'/'+fmt(c.bootstrap_requested)+'.</p>';
const f=D.flows[c.uf+'-'+c.municipality_code]||[];
if(f.length){h+='<h3>Model estimates (fractional expected voters)</h3>'+table(['Model','Origin','Destination','Estimate','Bootstrap 2.5%','Bootstrap 97.5%'],f.map(r=>[r.model,names[r.origin],names[r.destination],r.estimated_voters,r.bootstrap_p025,r.bootstrap_p975]));}
document.querySelector('#detail').innerHTML=h;document.querySelector('#detail').scrollIntoView({behavior:'smooth'});}
document.querySelector('#search').oninput=()=>{page=0;render()};document.querySelector('#sort').onchange=()=>{page=0;render()};
document.querySelector('#previous').onclick=()=>{page=Math.max(0,page-1);render()};document.querySelector('#next').onclick=()=>{page++;render()};render();
</script></html>"""
    replacements = {"YEAR": str(metadata["year"]), "NAMEA": escape(metadata["finalists"]["a"]["name"]),
                    "NAMEB": escape(metadata["finalists"]["b"]["name"]),
                    "NUMBERA": str(metadata["finalists"]["a"]["number"]), "NUMBERB": str(metadata["finalists"]["b"]["number"]),
                    "NCITIES": f"{len(cities):,}", "NSECTIONS": f"{pairs.analysis_eligible.sum():,}",
                    "NMODELS": f"{good:,}", "NDRAWS": str(metadata["bootstrap"]), "FIGURE": image, "PAYLOAD": payload}
    for key, value in replacements.items():
        html = html.replace(key, value)
    (output / "report.html").write_text(html)
