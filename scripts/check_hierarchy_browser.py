"""Exercise the actual offline report: controls, missingness, units and places."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]


def check(folder):
    folder=Path(folder).resolve()
    errors=[]
    data=json.loads((folder/"visualization_data.json").read_text())
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        page=browser.new_page(viewport={"width":1550,"height":1200})
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto((folder/"report.html").as_uri(),wait_until="load")
        expect(page.locator('#map .pilot')).to_have_count(12)
        expect(page.locator('#selected-title')).to_contain_text("LEBON RÉGIS")
        expect(page.locator('#detail')).to_contain_text("posterior credible interval")
        gray=page.locator('#map .area:not(.pilot)').first
        expect(gray).to_have_attribute('data-value','missing')
        original=page.locator('#map [data-key="81914"]').get_attribute('data-value')
        for metric in ['width','coverage','sensitivity','fit','calibration','rhat','status','disagreement','difference','flag']:
            page.locator('#metric').select_option(metric)
            expect(page.locator('#detail')).to_contain_text("95% interval")
            expect(gray).to_have_attribute('data-value','missing')
        page.locator('#metric').select_option('estimate')
        assert page.locator('#map [data-key="81914"]').get_attribute('data-value')==original
        page.locator('#units').select_option('rate')
        expect(page.locator('#detail')).to_contain_text('% of origin')
        flow=next(r for r in data['flows'] if r['municipality_code']==81914 and r['level']=='municipality'
                  and r['method']=='hierarchical' and r['origin']=='abstention' and r['destination']=='a')
        actual=float(page.locator('#map [data-key="81914"]').get_attribute('data-value'))
        assert abs(actual-flow['rate']*100)<1e-6
        page.locator('#method').select_option('municipal_baseline')
        expect(page.locator('#detail')).to_contain_text('bootstrap percentile sensitivity')
        page.locator('#metric').select_option('sensitivity')
        expect(page.locator('#map [data-key="81914"]')).to_have_attribute('data-value','missing')
        page.locator('#method').select_option('hierarchical')
        page.locator('#metric').select_option('estimate')
        page.locator('#extent').select_option('selected')
        assert page.locator('#map .pilot:visible').count()==1
        place=page.locator('#place option').nth(1).get_attribute('value')
        page.locator('#place').select_option(place)
        expect(page.locator('#detail')).to_contain_text('Municipal flags are not measured place-level disagreement')
        page.locator('#origin').select_option('other')
        page.locator('#destination').select_option('abstention')
        expect(page.locator('#detail')).to_contain_text('Other candidates → Abstention')
        page.locator('#city').select_option('7633')
        expect(page.locator('#selected-title')).to_contain_text('CODÓ')
        expect(page.locator('#place')).to_have_value('municipality')
        assert page.locator('#comparison tbody tr').count()==12
        assert page.locator('#charts svg').count()==3
        assert page.locator('#simulation tbody tr').count()>=16
        page.locator('#validation-level').select_option('place:sparse')
        expect(page.locator('#simulation')).to_contain_text('independent_place / place')
        expect(page.locator('#simulation')).to_contain_text('hierarchical / place')
        page.locator('#validation-level').select_option('municipality:all')
        page.screenshot(path=str(folder/'browser-preview.png'),full_page=True)
        browser.close()
    assert not errors,errors
    (folder/'browser_checks.json').write_text(json.dumps({"passed":True,"page_errors":errors,
          "checks":["12 verified municipality joins","all map metrics","missing outside-pilot data", "method-specific interval labels",
                    "rate denominators","unavailable baseline sensitivity","municipality-only map extent","local table selector",
                    "origin/destination changes","paired views","simulation table"]},indent=2))
    print('Offline report browser checks passed')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'results/2026/hierarchy_pilot')
    check(parser.parse_args().output)
