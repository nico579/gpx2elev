"""Exercise real cached OSM analysis and route rendering in a browser, offline."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gpx2elev.core import parse_gpx, prepare  # noqa: E402
from gpx2elev.obstacles import cache_path  # noqa: E402
from gpx2elev.providers import ProfileCache, Source  # noqa: E402
from gpx2elev.web import Application, start_server  # noqa: E402


def check(args):
    from playwright.sync_api import sync_playwright, expect
    args.output.mkdir(parents=True, exist_ok=True)
    coordinates = [(45, 5), (45.001, 5.001), (45.001, 5.003), (45.003, 5.004)]
    gpx = '<gpx version="1.1"><trk><trkseg>' + ''.join(
        f'<trkpt lat="{lat}" lon="{lon}"><ele>{100 + i * 10}</ele></trkpt>'
        for i, (lat, lon) in enumerate(coordinates)) + '</trkseg></trk></gpx>'
    gate = {"type": "node", "id": 1001, "lat": 45.0005, "lon": 5.0005,
            "tags": {"barrier": "gate", "foot:forward": "no", "foot:backward": "yes"}}
    unknown = {"type": "node", "id": 1002, "lat": 45.001, "lon": 5.002, "tags": {"barrier": "gate"}}
    fence = {"type": "way", "id": 2001, "nodes": [2002, 2003], "tags": {"barrier": "fence"},
             "geometry": [{"lat": 45.002, "lon": 5.003}, {"lat": 45.002, "lon": 5.005}]}
    road = {"type": "way", "id": 3001, "nodes": [3002, 1001, 3003], "tags": {"highway": "path"},
            "geometry": [{"lat": 45, "lon": 5}, {"lat": 45.0005, "lon": 5.0005}, {"lat": 45.001, "lon": 5.001}]}
    errors = []
    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        track = directory / "obstacles-demo.gpx"
        track.write_text(gpx, encoding="utf-8")
        prepared = prepare(parse_gpx(track))
        ProfileCache(directory / "profiles").save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
        cache = cache_path(prepared, directory)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"fetched_at": time.time(), "elements": [gate, unknown, fence, road]}), encoding="utf-8")
        app = Application(directory, online=False)
        server, port = start_server(app)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=args.browser_channel, headless=True)
                page = browser.new_page(viewport={"width": 1200, "height": 900}, locale="fr-FR")
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{port}/")
                expect(page.locator("#import")).to_be_enabled()
                page.set_input_files("#file", str(track))
                expect(page.locator("#obstacle-alert")).to_contain_text("2 blocage(s)")
                expect(page.locator("#obstacle-list li")).to_have_count(3)
                expect(page.locator("#obstacle-freshness")).to_contain_text("cache")
                page.locator("#route-panel").screenshot(path=str(args.output / "obstacles-fr.png"))
                original = page.evaluate("routeMap.zoomLevel")
                page.locator("#route-zoom-in").click()
                assert page.evaluate("routeMap.zoomLevel") > original
                page.locator("#obstacle-list button").first.click()
                expect(page.locator("#obstacle-list li.selected")).to_have_count(1)
                zoom = page.evaluate("routeMap.zoomLevel")
                page.locator("#route-reverse").check()
                expect(page.locator("#obstacle-alert")).to_contain_text("1 blocage(s)")
                expect(page.locator("#obstacle-list li")).to_have_count(2)
                assert page.evaluate("routeMap.reverse") is True
                assert page.evaluate("routeMap.zoomLevel") == zoom
                expect(page.locator("#obstacle-list li").first).to_contain_text("Clôture")
                page.locator("#route-reset").click()
                page.locator("#route-panel").screenshot(path=str(args.output / "obstacles-reverse.png"))
                page.get_by_role("button", name="EN", exact=True).first.click()
                expect(page.locator("#obstacle-alert")).to_contain_text("reported blockage")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator("#route-panel").screenshot(path=str(args.output / "obstacles-mobile-en.png"))
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert page.evaluate("routeMap.canvas.width > 0 && routeMap.events.length === 2")
                assert not errors, errors
                browser.close()
        finally:
            app.close()
            server.shutdown()
            server.server_close()
    print("Obstacle browser QA: import, cached detection, red/orange events, reverse permissions, selection, zoom, FR/EN and mobile layout OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-channel")
    parser.add_argument("--output", type=Path, default=ROOT / "qa/obstacles")
    check(parser.parse_args())
