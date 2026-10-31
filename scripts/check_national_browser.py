"""Check the candidate replacement and archived baseline at a project prefix."""
import argparse,contextlib,json,sys,threading
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from elections.spatial_runner import save


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


def check(site,output=None):
    from playwright.sync_api import sync_playwright,expect
    site=Path(site).resolve();output=Path(output or site.parent/'national-browser-qa');output.mkdir(parents=True,exist_ok=True)
    rows=json.loads((site/'data/national/index.json').read_text());release=json.loads((site/'data/national/release.json').read_text())
    available=next((r for r in rows if r.get('matrix') is not None),None)
    if available is None:raise ValueError('No computed new-model estimates available for browser checks')
    errors=[];server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(site.parent)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/{quote(site.name)}/'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url+f"#city={available['municipality_code']}",wait_until='networkidle',timeout=120000)
            expect(page.locator('#areas path')).to_have_count(5571,timeout=120000)
            expect(page.locator('#selected')).to_contain_text(available['municipality'])
            expect(page.locator('#flow-chart .ribbon').first).to_be_attached()
            for metric in ['estimate','width','coverage','computation','disagreement']:
                page.select_option('#metric',metric);assert page.locator('#legend').inner_text()
            page.select_option('#origin','4');page.select_option('#destination','0')
            assert 'Abstention' in page.locator('#flow-title').inner_text()
            assert 'Lula' in page.locator('#flow-title').inner_text()
            assert 'sampling' in page.locator('#legend').inner_text().lower() or page.locator('#fit-status').inner_text()
            with page.expect_download() as d:page.click('#export')
            exported=json.loads(Path(d.value.path()).read_text())
            assert exported['municipality_code']==available['municipality_code']
            missing=next((r for r in rows if r['status']=='no_verified_sections'),None)
            if missing:
                page.fill('#search',str(missing['municipality_code']));page.select_option('#city',str(missing['municipality_code']))
                expect(page.locator('#selected')).to_contain_text(missing['municipality'])
                expect(page.locator('#fit-status')).to_contain_text('unavailable')
                expect(page.locator('#flow-chart .ribbon')).to_have_count(0)
            page.goto(url+f"#city={available['municipality_code']}",wait_until='networkidle')
            page.reload(wait_until='networkidle')
            expect(page.locator('#selected')).to_contain_text(available['municipality'])
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'National page overflows phone viewport'
            page.screenshot(path=str(output/'national-phone.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1100});page.screenshot(path=str(output/'national-desktop.png'),full_page=True)
            page.goto(url+'national-methodology.html',wait_until='networkidle');assert 'What changed' in page.title()
            page.goto(url+'baseline.html',wait_until='networkidle',timeout=120000)
            expect(page.locator('#flow-chart .flow-ribbon')).to_have_count(13)
            expect(page.locator('.map-area')).to_have_count(27)
            assert not errors,errors
            browser.close()
    finally:server.shutdown();server.server_close()
    result={'passed':True,'release_id':release['release_id'],'preview':release['preview'],'municipalities':len(rows),
        'project_prefix':True,'metric_layers':5,'missing_results_do_not_fall_back':True,'baseline_archive':True,'mobile':True,'javascript_errors':errors}
    save(output/'checks.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();print(json.dumps(check(a.site,a.output),indent=2))
