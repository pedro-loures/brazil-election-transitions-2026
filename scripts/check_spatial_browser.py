"""Browser checks for metric selectors, scope labels, missing values and exports."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from elections.spatial import OUT
from elections.spatial_runner import save


def check(output=OUT):
    output=Path(output);errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1100})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto((output/'report.html').as_uri(),wait_until='load',timeout=120000)
        page.wait_for_selector('#map path')
        assert page.locator('#city option').count()==48
        assert 'unobserved' in page.locator('body').inner_text()
        for metric in ['estimate','width','full_data_coverage','data_coverage','sensitivity','convergence','disagreement','coverage']:
            page.select_option('#metric',metric)
            assert page.locator('#legend').inner_text()
        assert page.locator('#evidence').input_value()=='validation'
        for phase in ['development','confirmation','validation']:
            page.select_option('#evidence',phase)
            assert 'scope:' in page.locator('#detail').inner_text()
        page.select_option('#level','group')
        assert page.locator('#map circle').count()>0
        page.select_option('#metric','estimate')
        for method in ['municipal_wls','municipal_bayes','administrative','geographic_extended']:
            page.select_option('#method',method)
            assert 'Computation:' in page.locator('#detail').inner_text()
        page.select_option('#city',index=47)
        assert page.locator('#map circle').count()>0
        with page.expect_download() as download:
            page.click('#download')
        path=download.value.path()
        data=json.loads(Path(path).read_text())
        assert 'selection' in data and 'values' in data
        page.select_option('#level','municipality')
        page.select_option('#metric','full_data_coverage')
        page.screenshot(path=str(output/'browser-preview.png'),full_page=True)
        assert not errors,errors
        browser.close()
    save(output/'browser_checks.json',{'passed':True,'errors':errors,'municipalities':48,'metric_layers':8,
        'group_points_and_network':True,'download_config_and_data':True})


if __name__=='__main__':check()
