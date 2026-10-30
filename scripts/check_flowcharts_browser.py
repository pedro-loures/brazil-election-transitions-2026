"""Optional Playwright QA for the localhost flow explorer."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def check(url, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1500, "height": 1200}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto(url, wait_until="networkidle")
        assert response.status == 200
        expect(page.locator(".flow-ribbon[role=button]")).to_have_count(13)
        assert "8,737" in page.locator("#scope").inner_text()
        assert "604" in page.locator("#gain-charts").inner_text()
        flow = page.locator('.flow-ribbon[role=button][data-link="4-0"]')
        flow.focus(); flow.press("Enter")
        expect(page.locator("#flow-value")).to_have_text("478")
        assert "Abstention" in page.locator("#flow-title").inner_text()
        page.locator("#clear-selection").click()
        expect(page.locator("#flow-title")).to_have_text("Choose a flow")
        page.locator(".workspace").screenshot(path=str(output / "thread-sankey.png"))
        page.locator("#view-schematic").click()
        expect(page.locator(".flow-line[role=button]")).to_have_count(13)
        assert "2,818 retained" in page.locator("#flow-chart").text_content()
        assert page.locator(".flow-number").count() >= 10
        page.locator(".workspace").screenshot(path=str(output / "thread-arrows.png"))
        with page.expect_download() as download:
            page.locator("#download-svg").click()
        download.value.save_as(str(output / "export.svg"))
        assert "<svg" in (output / "export.svg").read_text()
        page.locator("#minimum-flow").fill("500")
        expect(page.locator(".flow-line[role=button]")).to_have_count(3)
        page.locator("#show-retained").uncheck()
        expect(page.locator(".flow-line[role=button]")).to_have_count(0)
        page.locator("#minimum-flow").fill("0")
        page.locator("#show-retained").check()
        page.locator("#source-municipality").click()
        expect(page.locator("#coverage")).to_contain_text("29 / 30")
        assert "Our reconstruction" in page.locator("#provenance").inner_text()
        estimate=page.locator('.flow-line[role=button][data-link="4-0"]')
        estimate.focus();estimate.press("Enter")
        expect(page.locator("#flow-details")).to_contain_text("Section-bootstrap range")
        assert page.locator("#flow-value").inner_text() != "478"
        page.locator("#model").select_option("no_cross")
        expect(page.locator("#source-label")).to_contain_text("NO FINALIST SWITCHING")
        page.locator("#city-search").fill("sao paulo")
        page.locator("#city-options").select_option("71072")
        expect(page.locator("#city-title")).to_have_text("SÃO PAULO, SP")
        page.locator("#model").select_option("full")
        page.locator(".workspace").screenshot(path=str(output / "sao-paulo-arrows.png"))
        index=page.request.get(url.rstrip('/')+'/data/index.json').json()
        skipped=next(c for c in index if c["model_status"] != "ok")
        page.locator("#city-search").fill(str(skipped["municipality_code"]))
        page.locator("#city-options").select_option(str(skipped["municipality_code"]))
        expect(page.locator("#empty-chart")).to_be_visible()
        expect(page.locator("#totals-body tr")).to_have_count(6)
        page.locator("#aggregate-level").select_option("state")
        expect(page.locator("#city-title")).to_have_text("Minas Gerais")
        expect(page.locator("#coverage")).to_contain_text("853 municipalities")
        expect(page.locator("#provenance")).to_contain_text("summed")
        expect(page.locator("#observed-round-one")).to_contain_text("full state")
        assert page.locator(".flow-line[role=button]").count() > 0
        state_payload=page.request.get(url.rstrip('/')+'/data/aggregates/state-MG.json').json()
        expected_sum=sum(sum(row) for row in state_payload["models"]["full"]["matrix"])
        assert abs(expected_sum-state_payload["models"]["full"]["coverage"]["analyzed_eligible_1"])<.001
        page.locator("#aggregate-level").select_option("region")
        expect(page.locator("#city-title")).to_have_text("Northeast · Nordeste")
        expect(page.locator("#observed-round-one")).to_contain_text("full region")
        page.locator("#aggregate-level").select_option("country")
        expect(page.locator("#city-title")).to_have_text("Brazil · domestic electorate")
        expect(page.locator("#coverage")).to_contain_text("5,571 municipalities")
        country_flow=page.locator('.flow-line[role=button][data-link="1-0"]')
        country_flow.focus();country_flow.press("Enter")
        expect(page.locator("#flow-details")).to_contain_text("Not computed for this aggregate")
        assert "419,961" in page.locator("#flow-value").inner_text()
        page.locator("#view-sankey").click()
        page.locator(".workspace").screenshot(path=str(output / "brazil-sankey.png"))
        page.locator("#model").select_option("no_cross")
        expect(page.locator("#source-label")).to_contain_text("NO FINALIST SWITCHING")
        expect(page.locator('.flow-ribbon[role=button][data-link="1-0"]')).to_have_count(0)
        page.reload(wait_until="networkidle")
        expect(page.locator("#city-title")).to_have_text("Brazil · domestic electorate")
        expect(page.locator("#model")).to_have_value("no_cross")
        page.locator("#source-thread").click()
        page.locator("#view-sankey").click()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Page overflows phone viewport"
        page.wait_for_function("[...document.querySelectorAll('#gain-charts .chart-label')].every(n => n.getBoundingClientRect().height >= 10)")
        page.screenshot(path=str(output / "phone.png"), full_page=True)
        page.set_viewport_size({"width": 1500, "height": 1200})
        page.emulate_media(color_scheme="dark")
        page.locator(".workspace").screenshot(path=str(output / "dark-sankey.png"))
        assert not errors, errors
        browser.close()
    print(json.dumps({"browser_checks": "passed", "javascript_errors": errors, "screenshots": str(output)}, indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765/")
    parser.add_argument("--output", default="results/2026/flowcharts-qa")
    args=parser.parse_args()
    check(args.url,args.output)
