"""Browser checks for geographic selection and observed-result colors."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def click_inside(page, key):
    path = page.locator(f'.map-area[data-key="{key}"]')
    path.scroll_into_view_if_needed()
    point = path.evaluate("""path=>{
      const box=path.getBBox(),p=path.ownerSVGElement.createSVGPoint();
      const steps=[10,9,11,8,12,7,13,6,14,5,15,4,16,3,17,2,18,1,19];
      for(const i of steps)for(const j of steps){
        p.x=box.x+box.width*i/20;p.y=box.y+box.height*j/20;
        if(path.isPointInFill(p)){
          const q=p.matrixTransform(path.getScreenCTM());
          if(document.elementFromPoint(q.x,q.y)===path)return {x:q.x,y:q.y};
        }
      }
      throw Error('No interior map point found');
    }""")
    page.mouse.click(point["x"], point["y"])


def check(url, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1500, "height": 1200})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="networkidle")
        expect(page.locator(".map-area")).to_have_count(27)
        expect(page.locator("#map-scale")).to_have_value("log")
        expect(page.locator(".map-boundary-state")).to_have_count(27)
        expect(page.locator(".map-boundary-region")).to_have_count(5)
        click_inside(page, "MG")
        expect(page.locator("#city-title")).to_have_text("Minas Gerais")
        expect(page.locator('.map-area[data-key="MG"]')).to_have_attribute("aria-pressed", "true")
        mg = page.request.get(url+"data/aggregates/state-MG.json").json()["city"]
        expected = int((mg["a_2"]-mg["a_1"])-(mg["b_2"]-mg["b_1"]))
        assert page.locator('.map-area[data-key="MG"]').get_attribute("data-delta") == str(expected)
        expected_label=('Lula' if expected>0 else 'Flávio')+f' +{abs(expected):,}'
        assert page.locator("#map-margin-change").inner_text() == expected_label
        log_fill=page.locator('.map-area[data-key="MG"]').get_attribute("fill")
        page.locator("#map-scale").select_option("linear")
        expect(page.locator("#map-scale-note")).to_contain_text("linear")
        assert page.locator('.map-area[data-key="MG"]').get_attribute("fill")!=log_fill
        assert page.locator("#map-margin-change").inner_text()==expected_label
        page.locator("#map-scale").select_option("log")
        page.locator("#map-selected").click()
        transform = page.locator("#map-areas").get_attribute("transform")
        page.locator("#map-zoom-in").click()
        assert page.locator("#map-areas").get_attribute("transform") != transform
        page.locator("#map-reset").click()
        assert page.locator("#map-areas").get_attribute("transform") == "translate(0 0) scale(1)"
        page.locator(".map-section").screenshot(path=str(output/"map-states.png"))

        page.locator("#map-level").select_option("region")
        expect(page.locator(".map-area")).to_have_count(5)
        expect(page.locator(".map-boundary-state")).to_have_count(27)
        widths=page.evaluate("[getComputedStyle(document.querySelector('.map-boundary-state')).strokeWidth,getComputedStyle(document.querySelector('.map-boundary-region')).strokeWidth].map(parseFloat)")
        assert widths[0]<widths[1]<=1
        click_inside(page, "northeast")
        expect(page.locator("#city-title")).to_have_text("Northeast · Nordeste")
        expect(page.locator("#aggregate-level")).to_have_value("region")
        page.locator(".map-section").screenshot(path=str(output/"map-regions.png"))

        page.locator("#map-level").select_option("municipality")
        expect(page.locator(".map-area")).to_have_count(5571)
        expect(page.locator(".map-boundary-state")).to_have_count(27)
        page.locator("#map-filter").select_option("SC")
        expect(page.locator(".map-area")).to_have_count(295)
        click_inside(page, "81914")
        expect(page.locator("#city-title")).to_have_text("LEBON RÉGIS, SC")
        expect(page.locator("#map-margin-change")).to_have_text("Lula +368")
        expect(page.locator("#map-delta-lula")).to_have_text("+604")
        expect(page.locator("#map-delta-flavio")).to_have_text("+236")
        expect(page.locator("#coverage")).to_contain_text("29 / 30")
        before=page.locator("#map-margin-change").inner_text()
        page.locator("#model").select_option("no_cross")
        expect(page.locator("#source-label")).to_contain_text("NO FINALIST SWITCHING")
        assert page.locator("#map-margin-change").inner_text()==before
        page.locator(".map-section").screenshot(path=str(output/"map-municipalities.png"))
        # Keyboard activation and signed color values both remain available.
        key=page.locator('.map-area:not([data-key="81914"])').first.get_attribute("data-key")
        other=page.locator(f'.map-area[data-key="{key}"]')
        other.focus();other.press("Enter")
        expect(other).to_have_attribute("aria-pressed", "true")
        page.locator("#map-filter").select_option("MT")
        expect(page.locator('.map-area[data-key="73709"]')).to_have_count(1)
        click_inside(page,"73709")
        expect(page.locator("#city-title")).to_have_text("BOA ESPERANÇA DO NORTE, MT")
        page.locator("#map-filter").select_option("")
        expect(page.locator(".map-area")).to_have_count(5571)
        assert page.locator('.map-area[data-delta^="-"]').count()>0
        negative=page.locator('.map-area[data-delta^="-"]').first
        negative_key=negative.get_attribute("data-key")
        negative_advantage=abs(int(negative.get_attribute("data-delta")))
        negative=page.locator(f'.map-area[data-key="{negative_key}"]')
        negative.focus();negative.press("Enter")
        expect(page.locator("#map-margin-change")).to_have_text(f'Flávio +{negative_advantage:,}')
        page.locator(".map-section").screenshot(path=str(output/"map-brazil-log.png"))
        page.locator("#map-country").click()
        expect(page.locator("#city-title")).to_have_text("Brazil · domestic electorate")
        page.reload(wait_until="networkidle")
        expect(page.locator(".map-area")).to_have_count(27)
        expect(page.locator("#city-title")).to_have_text("Brazil · domestic electorate")
        page.set_viewport_size({"width":390,"height":844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Map overflows phone viewport"
        page.locator(".map-section").screenshot(path=str(output/"map-phone.png"))
        page.emulate_media(color_scheme="dark")
        page.locator(".map-section").screenshot(path=str(output/"map-dark.png"))
        assert not errors,errors
        browser.close()
    print(json.dumps({"map_browser_checks":"passed","javascript_errors":errors,"screenshots":str(output)},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8765/")
    parser.add_argument("--output",default="results/2026/flowcharts-qa")
    args=parser.parse_args();check(args.url,args.output)
