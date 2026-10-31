"""Exercise all actual agreement-map selectors and data export."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from elections.agreement_runner import OUT
from elections.spatial_runner import save
from playwright.sync_api import sync_playwright


def check(output=OUT):
    output=Path(output);errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1100})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto((output/'report.html').as_uri(),wait_until='load',timeout=120000)
        assert page.locator('#city option').count()>0
        for metric in ['range','agreement','bootstrap','sd','prior','width','estimate']:
            page.select_option('#metric',metric);assert page.locator('#legend').inner_text()
        for support in ['municipality','original_place','section']:
            page.select_option('#support',support)
            assert page.locator('#map circle').count()>0
            assert page.locator('#unit option').count()>0
        for family in ['municipal','geographic','behavioural','combined']:page.select_option('#family',family)
        page.select_option('#support','municipality');page.select_option('#metric','range')
        with page.expect_download() as d:page.click('#export')
        data=json.loads(Path(d.value.path()).read_text());assert 'selection' in data and 'values' in data
        page.screenshot(path=str(output/'browser-preview.png'),full_page=True)
        assert not errors,errors
        browser.close()
    save(output/'browser_checks.json',{'passed':True,'errors':errors,'metric_layers':7,'fixed_supports':3,'families':4,'export':True})


if __name__=='__main__':check()
