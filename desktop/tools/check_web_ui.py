"""Browser regression of the same user workflows as the former desktop window.

Install requirements-test.txt and Chromium, then run this from desktop/.
--browser-channel msedge uses the installed Edge for local Windows QA.
--executable dist/gpx2elev/gpx2elev.exe tests the actual packaged server and assets.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gpx2elev.core import parse_gpx, prepare
from gpx2elev.providers import Cancelled, ProfileCache, Source
from gpx2elev.smoke import SYNTHETIC_GPX
from gpx2elev.web import Application, start_server


def check(args):
    from playwright.sync_api import sync_playwright, expect
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        track = root / "randonnée.gpx"
        track.write_bytes(SYNTHETIC_GPX)
        prepared = prepare(parse_gpx(track))
        ProfileCache(root / "profiles").save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
        app = server = process = None
        if args.executable:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            process = subprocess.Popen([str(args.executable.resolve()), "--offline", "--data-dir", str(root),
                                        "--port", str(port), "--no-browser", "--no-tray"])
        else:
            app = Application(root, online=False)
            server, port = start_server(app)
        url = f"http://127.0.0.1:{port}/"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(route):
            with opener.open(url + route, timeout=3) as response:
                return json.load(response)
        deadline = time.monotonic() + 20
        while True:
            try:
                request("api/init")
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise AssertionError("Packaged server failed to start")
                time.sleep(.1)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=args.browser_channel, headless=True)
                context = browser.new_context(viewport={"width": 1339, "height": 667}, locale="fr-FR", accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.on("response", lambda response: errors.append(f"HTTP {response.status} {response.url}") if response.status >= 400 else None)
                page.goto(url)
                expect(page.locator("#import")).to_be_enabled()
                expect(page.get_by_role("button", name="FR", exact=True)).to_have_attribute("aria-pressed", "true")
                expect(page.locator("#chart-empty")).to_be_visible()
                page.screenshot(path=str(output / "empty.png"), full_page=True)

                page.locator("#online").uncheck()
                page.set_input_files("#file", str(track))
                expect(page.locator("#status")).to_contain_text("Calcul terminé")
                expect(page.locator("#up")).to_have_text("+22 m")
                expect(page.locator("#down")).to_have_text("−0 m")
                expect(page.locator("#filename")).to_have_text("randonnée.gpx")
                expect(page.locator("#export-summary")).to_be_enabled()
                original = request("api/result")
                assert original["summary"]["depuis_cache"]
                checks.append("browser file picker, offline calculation and same values")

                for kind, count in (("summary", 4), ("profile", prepared.sample_count + 1)):
                    with page.expect_download() as event:
                        page.locator("#export-" + kind).click()
                    download = event.value
                    destination = output / download.suggested_filename
                    download.save_as(destination)
                    data = destination.read_bytes()
                    assert data.startswith(b"\xef\xbb\xbf")
                    assert len(data.decode("utf-8-sig").splitlines()) == count
                checks.append("real browser downloads: results and full-resolution profile CSV")

                rect = page.locator("#chart").bounding_box()
                canvas = page.locator("#chart")
                canvas.click(position={"x": 62 + (rect["width"] - 82) / 2, "y": rect["height"] / 2})
                expect(page.locator("#selection")).to_contain_text("Mesure GPX : 110,0 m")
                expect(page.locator("#selection")).to_contain_text(time.strftime("%H:%M:%S", time.localtime(original["chart"]["native"]["time"][1])))
                selected = page.evaluate("plot.selection")
                bounds = page.evaluate("plot.bounds")
                page.locator("#zoom-in").click()
                zoom = page.evaluate("plot.view")
                assert zoom[1] - zoom[0] < bounds[1] - bounds[0]
                assert page.evaluate("plot.selection") == selected
                rect = canvas.bounding_box()
                page.mouse.move(rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2)
                page.mouse.down()
                page.mouse.move(rect["x"] + rect["width"] / 2 + 35, rect["y"] + rect["height"] / 2 + 10, steps=5)
                page.mouse.up()
                assert page.evaluate("plot.view") != zoom
                page.mouse.wheel(0, -120)
                assert page.evaluate("plot.view[1]-plot.view[0]") < zoom[1] - zoom[0]
                page.locator("#reset").click()
                assert page.evaluate("plot.view") == bounds
                canvas.press("+")
                assert page.evaluate("plot.view") != bounds
                canvas.press("Home")
                assert page.evaluate("plot.view") == bounds
                checks.append("cursor with native GPX time, zoom, wheel, pan, reset and keyboard")

                page.locator("#zoom-in").click()
                view = page.evaluate("plot.view")
                page.locator("#fullscreen").click()
                page.wait_for_function("!!document.fullscreenElement || document.getElementById('plot-panel').classList.contains('expanded')")
                assert page.evaluate("plot.view") == view
                page.screenshot(path=str(output / "fullscreen.png"))
                page.locator("#plot-panel").get_by_role("button", name="EN", exact=True).click()
                expect(page.locator("#import")).to_have_text("Choose a GPX")
                expect(page.locator("#fullscreen")).to_have_text("Exit full screen")
                expect(page.locator("#selection")).to_contain_text("GPX measurement: 110.0 m")
                assert page.evaluate("plot.selection") == selected
                page.locator("#fullscreen").click()
                page.wait_for_function("!document.fullscreenElement && !document.getElementById('plot-panel').classList.contains('expanded')")
                assert page.evaluate("plot.view") == view
                assert request("api/result") == original
                expect(page.locator(".comparison h2")).to_have_text("GPX comparison")
                expect(page.locator("#cache")).to_contain_text("Profiles")
                expect(page.locator("#cache")).to_contain_text("Tiles")
                page.screenshot(path=str(output / "english.png"), full_page=True)
                page.get_by_role("button", name="FR", exact=True).click()
                expect(page.locator("#import")).to_have_text("Choisir un GPX")
                checks.append("fullscreen and FR/EN preserve zoom, cursor and calculation")

                for width, height in ((1339, 667), (800, 500), (390, 844)):
                    page.set_viewport_size({"width": width, "height": height})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, height)
                    for id in ("up", "down", "length"):
                        assert page.locator("#" + id).evaluate("(el)=>el.scrollHeight<=el.clientHeight"), id
                    page.screenshot(path=str(output / f"layout-{width}x{height}.png"), full_page=True)
                page.set_viewport_size({"width": 1339, "height": 667})
                page.locator("#model").select_option("IGN")
                previous_revision = page.evaluate("revision")
                page.locator("#recalculate").click()
                page.wait_for_function("(before)=>currentState.revision>before && !currentState.busy && !!currentResult", arg=previous_revision)
                expect(page.locator("#status")).to_contain_text("Calcul terminé")
                assert request("api/result")["summary"]["terrain"] == original["summary"]["terrain"]
                checks.append("model selection and responsive layout without clipped values")

                invalid = root / "invalid.gpx"
                invalid.write_bytes(b"not xml")
                page.set_input_files("#file", str(invalid))
                expect(page.locator("#details")).to_be_visible()
                expect(page.locator("#source")).to_have_text("Aucun profil complet disponible")
                expect(page.locator("#export-summary")).to_be_disabled()
                dropped = page.evaluate_handle("(text)=>{const transfer=new DataTransfer();transfer.items.add(new File([text],'drop.gpx',{type:'application/gpx+xml'}));return transfer;}", SYNTHETIC_GPX.decode())
                page.locator("#dropzone").dispatch_event("drop", {"dataTransfer": dropped})
                expect(page.locator("#filename")).to_have_text("drop.gpx")
                expect(page.locator("#status")).to_contain_text("Calcul terminé")
                checks.append("invalid input feedback and real File/DataTransfer drop")

                if app:
                    entered = __import__("threading").Event()
                    def slow(path, directory, online, source, progress, cancel):
                        entered.set()
                        progress("Lecture des altitudes", 1, 10)
                        cancel.wait(10)
                        raise Cancelled()
                    with patch("gpx2elev.web.calculate", side_effect=slow):
                        page.locator("#recalculate").click()
                        expect(page.locator("#cancel")).to_be_visible()
                        expect(page.locator("#import")).to_be_disabled()
                        expect(page.locator("#clear-cache")).to_be_disabled()
                        page.locator("#cancel").click()
                        expect(page.locator("#status")).to_have_text("Calcul annulé.")
                        expect(page.locator("#import")).to_be_enabled()
                    previous_revision = page.evaluate("revision")
                    page.locator("#recalculate").click()
                    page.wait_for_function("(before)=>currentState.revision>before && !currentState.busy && !!currentResult", arg=previous_revision)
                    expect(page.locator("#status")).to_contain_text("Calcul terminé")
                    checks.append("background calculation, progress, disabled actions and cancellation")

                page.locator("#about").click()
                expect(page.locator("#about-dialog")).to_be_visible()
                page.locator("#about-dialog button.primary").click()
                checks.append("method, sources and dependency information")

                if app:
                    with patch("gpx2elev.update_web.UpdateClient.check", return_value=None):
                        page.locator("#updates").click()
                        expect(page.locator("#update-status")).to_have_text("Vous utilisez la dernière version publiée.")
                        page.locator("#update-dialog").get_by_role("button", name="EN", exact=True).click()
                        expect(page.locator("#update-status")).to_have_text("You are using the latest published version.")
                        expect(page.locator("#update-check")).to_have_text("Check again")
                        page.locator("#update-close").click()
                        page.get_by_role("button", name="FR", exact=True).click()
                    checks.append("manual update dialog, result and FR/EN")

                before = request("api/result")
                page.locator("#clear-cache").click()
                expect(page.locator("#confirm-dialog")).to_be_visible()
                page.locator("#confirm-dialog").get_by_role("button", name="Annuler", exact=True).click()
                assert sum(request("api/state")["cache"].values()) > 0
                page.locator("#clear-cache").click()
                page.locator("#confirm-action").click()
                expect(page.locator("#status")).to_have_text("Cache vidé.")
                expect(page.locator("#clear-cache")).to_be_disabled()
                assert request("api/result") == before
                expect(page.locator("#export-summary")).to_be_enabled()
                assert (root / "last.gpx").read_bytes() == SYNTHETIC_GPX
                checks.append("cache confirmation, cancellation and clearing preserve input and result")
                page.screenshot(path=str(output / "cache-cleared.png"), full_page=True)
                assert not errors, errors
                report = {"status": "OK", "browser": browser.version, "packaged": bool(args.executable), "checks": checks, "errors": errors}
                (output / "browser-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                context.close()
                browser.close()
        finally:
            if app:
                app.close()
                server.shutdown()
                server.server_close()
            if process:
                try:
                    req = urllib.request.Request(url + "api/quit", data=b"{}", headers={"Content-Type": "application/json"})
                    opener.open(req, timeout=3).close()
                    process.wait(timeout=15)
                except (OSError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-channel")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "qa/web")
    raise SystemExit(check(parser.parse_args()) or 0)
