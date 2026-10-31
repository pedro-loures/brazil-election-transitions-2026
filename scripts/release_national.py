"""Wait for the authorized national run, verify, build and publish to Pages.

Publication requires --publish and a prepared release-ready record. Git pushes
are ordinary fast-forwards. Changes to release sources stop automation.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,time,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from elections.national_combined import OUT,verify
from elections.spatial_runner import save


def command(args,cwd=ROOT,env=None):
    r=subprocess.run(list(map(str,args)),cwd=cwd,env=env,text=True,capture_output=True)
    if r.returncode:raise RuntimeError(f"Command failed ({r.returncode}): {args[0]}\n"+r.stdout[-2000:]+r.stderr[-2000:])
    return r.stdout.strip()


def package_inputs(results,checkout):
    """Publish processed shards and audit caches, not raw source archives/draws."""
    results=Path(results);destination=Path(checkout)/'datasets/2026/national_combined';destination.mkdir(parents=True,exist_ok=True)
    sources=list((results/'inputs').glob('*.npz'))+[results/'manifest.json']
    sources += [ROOT/'results/2026/spatial_pooling/manifest.json',ROOT/'results/2026/spatial_pooling/section_coordinates.csv.gz',
        ROOT/'results/2026/spatial_feasibility/municipality_population_bins.csv',ROOT/'results/2026/model_agreement/manifest.json',
        ROOT/'results/2026/model_agreement/decision.json']
    archive=destination/'reproduction-inputs.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(sources):
            rel=p.relative_to(ROOT);z.write(p,str(rel))
    if archive.stat().st_size>=90*1024**2:raise ValueError('Reproduction archive exceeds the publication size budget')
    shutil.copy2(results/'manifest.json',destination/'manifest.json');shutil.copy2(results/'verification.json',destination/'verification.json')
    save(destination/'snapshot.json',{'archive':'reproduction-inputs.zip','sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'raw_archives_included':False,'posterior_draws_included':False,'restore':'python scripts/restore_national_inputs.py'})
    (destination/'README.md').write_text('# National combined model snapshot\n\nRestore the existing baseline snapshot, then the frozen national inputs with `python scripts/restore_national_inputs.py`. Install `requirements-spatial.txt` in Python 3.10 and run `python -m elections.national_combined run --workers 8` to reproduce the computation. Source and input hashes are verified before fitting. Raw source archives and posterior draws are not included; the published site contains municipal point estimates, intervals, diagnostics and coverage.\n')
    return destination


def release(results=OUT,checkout=Path('/tmp/elections-national-release'),publish=False,wait=True):
    results=Path(results);checkout=Path(checkout)
    status_path=results/'publication_status.json'
    state={'status':'waiting_for_national_run','started_utc':datetime.now(timezone.utc).isoformat(),'publish_authorized':publish}
    def status(value,**fields):
        state.update(status=value,**fields,updated_utc=datetime.now(timezone.utc).isoformat());save(status_path,state)
    try:
        status('waiting_for_national_run')
        while True:
            run=json.loads((results/'execution_state.json').read_text())
            if run['status']=='controller_failed':raise ValueError('National computation controller failed')
            if run.get('publication_allowed') and run['status']=='completed' and run['pending_cities']==0:break
            if not wait:raise ValueError('National run is not complete')
            time.sleep(30)
        ready=json.loads((results/'release_ready.json').read_text())
        status('verifying_national_results');checks=verify(results)
        if not checks['complete']:raise ValueError('Incomplete national results')
        for rel,digest in ready['release_sources'].items():
            if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=digest:raise ValueError('Release source changed: '+rel)
        if not checkout.exists():raise ValueError('Prepared release checkout is missing')
        if command(['git','status','--porcelain'],checkout):raise ValueError('Release checkout is not clean')
        command(['git','fetch','origin','main'],checkout)
        command(['git','merge','--ff-only','origin/main'],checkout)
        parent=command(['git','rev-parse','HEAD'],checkout)
        command(['git','merge-base','--is-ancestor',ready['code_commit'],parent],checkout)
        for rel,digest in ready['release_sources'].items():
            if hashlib.sha256((checkout/rel).read_bytes()).hexdigest()!=digest:raise ValueError('Remote release source changed: '+rel)
        status('building_candidate_site',parent_commit=parent)
        from scripts.build_national_site import build
        candidate=results/'publication-candidate'
        built=build(results,candidate,checkout/'docs',False)
        package_inputs(results,checkout)
        status('checking_candidate_site',release_id=built['release_id'])
        browser_env=os.environ.copy();browser_env.update(PYTHONPATH=ready['browser_pythonpath'],PLAYWRIGHT_BROWSERS_PATH=ready['browser_path'],OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        command([sys.executable,ROOT/'scripts/check_national_browser.py','--site',candidate,'--output',results/'publication-browser-qa'],env=browser_env)
        command(['node',ROOT/'tests/test_flow_layout.mjs',candidate/'data'])
        if built['preview'] or built['terminal_records']!=5571:raise ValueError('A partial/preview site cannot be published')
        shutil.copytree(candidate,checkout/'docs',dirs_exist_ok=True)
        command(['git','add','--','docs','datasets/2026/national_combined'],checkout)
        if not publish:
            status('candidate_verified_not_published');return state
        # User explicitly authorized this main-branch commit and Pages release.
        message=('Publish nationwide geographic–behavioural transition model\n\n'
            'Replace the primary explorer after all 5,571 municipal units have terminal records. '
            'Publish conditional intervals, coverage and computational diagnostics; preserve unavailable cases and the baseline archive. '
            'Include frozen processed inputs, reproducibility hashes and pilot limitations. '
            'The release is experimental; nationwide independent calibration remains incomplete.')
        command(['git','commit','-m',message],checkout)
        commit=command(['git','rev-parse','HEAD'],checkout)
        status('pushing_national_release',commit=commit)
        command(['git','push','origin','HEAD:refs/heads/main'],checkout)
        status('waiting_for_github_pages',commit=commit)
        url=ready['pages_url'].rstrip('/')+'/data/national/release.json'
        for _ in range(120):
            try:
                request=urllib.request.Request(url+'?release='+built['release_id'],headers={'Cache-Control':'no-cache'})
                with urllib.request.urlopen(request,timeout=30) as response:live=json.load(response)
                if live.get('release_id')==built['release_id'] and not live.get('preview'):
                    with urllib.request.urlopen(ready['pages_url'],timeout=30) as response:html=response.read().decode()
                    if 'national-app.mjs' not in html:raise ValueError('Pages has not switched its primary page')
                    with urllib.request.urlopen(ready['pages_url'].rstrip('/')+'/baseline.html',timeout=30) as response:
                        if response.status!=200:raise ValueError('Baseline archive unavailable')
                    status('published',commit=commit,pages_url=ready['pages_url'],release_id=built['release_id']);return state
            except Exception as error:state['last_pages_check']=str(error)
            time.sleep(15)
        status('pushed_pages_verification_pending',commit=commit);return state
    except BaseException as error:
        status('release_failed',error=repr(error));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,default=OUT)
    p.add_argument('--checkout',type=Path,default=Path('/tmp/elections-national-release'));p.add_argument('--publish',action='store_true');p.add_argument('--no-wait',action='store_true')
    a=p.parse_args();print(json.dumps(release(a.results,a.checkout,a.publish,not a.no_wait),indent=2))
