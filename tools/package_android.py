"""Verify and package the APK built by GitHub Actions; no private fixtures required."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from check_versions import check, ROOT

CERTIFICATE = '2e1c7200c865dd127c22d2233feba41d5b9e9d1a81fbd2030a106e6d32c8e7ec'
OPTIONAL = {
    ('LiveModelsTest', 'allPublicSourcesAgreeWithAuditedLocalData'),
    ('ElevationMathTest', 'matchesAuditedPythonOnOctober4Trace'),
    ('AndroidUiTest', 'welcomeAndRealImportWithCachedIgn'),
    ('AndroidUiTest', 'resultInDarkMode'),
    ('AndroidUiTest', 'resultInLandscape'),
    ('AndroidUiTest', 'resultInEnglishKeepsGainAndFormatsDistance'),
}


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Release APKs must be built by GitHub Actions'
    version = check()
    results = [ET.parse(p).getroot() for p in (ROOT/'app/build/test-results/testDebugUnitTest').glob('TEST-*.xml')]
    counts = {key: sum(int(r.get(key, '0')) for r in results) for key in ('tests','failures','errors','skipped')}
    assert counts['tests'] == 23 and counts['failures'] == counts['errors'] == 0, counts
    skipped = [(c.get('classname','').rsplit('.',1)[-1], c.get('name',''))
               for r in results for c in r.findall('testcase') if c.find('skipped') is not None]
    assert set(skipped) <= OPTIONAL and counts['tests']-counts['skipped'] >= 17, skipped
    lint = ET.parse(ROOT/'app/build/reports/lint-results-release.xml').getroot().findall('issue')
    assert not any(i.get('severity') in ('Error','Fatal') for i in lint)

    apk = ROOT/'app/build/outputs/apk/release/app-release.apk'
    with zipfile.ZipFile(apk) as archive:
        fixtures = {p.name for p in (ROOT/'app/src/test/resources').iterdir() if p.is_file()}
        assert not any(Path(n).name in fixtures for n in archive.namelist()), 'Test fixture in APK'
        assert 'assets/translations.json' in archive.namelist()
        assert not any(n.endswith('.keystore') for n in archive.namelist())

    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ['ANDROID_SDK_ROOT'])
    tools = sdk/'build-tools/34.0.0'
    aapt = tools/('aapt.exe' if os.name == 'nt' else 'aapt')
    signer = tools/('apksigner.bat' if os.name == 'nt' else 'apksigner')
    badging = subprocess.check_output([str(aapt),'dump','badging',str(apk)], text=True)
    metadata = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
    assert metadata and metadata[1] == 'com.nico.gpx2elev' and metadata[3] == version, badging.splitlines()[0]
    signed = subprocess.check_output([str(signer),'verify','--print-certs',str(apk)], text=True)
    fingerprint = re.search(r'certificate SHA-256 digest: ([0-9a-f]+)', signed)
    assert fingerprint and fingerprint[1] == CERTIFICATE, 'Unexpected Android signing certificate'

    output = ROOT/'release'
    output.mkdir(exist_ok=True)
    target = output/f'gpx2elev-{version}.apk'
    shutil.copy2(apk,target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    report = {'application':'gpx2elev','version':version,'application_id':metadata[1],
              'versionCode':int(metadata[2]),'languages':['fr','en'],'sha256':digest,
              'certificat_signataire_sha256':fingerprint[1],'tests':counts,'tests_optionnels_ignores':skipped,
              'lint_erreurs':0,'lint_avertissements':len(lint),
              'fixtures_personnelles_exclues_APK':True,
              'validation':'GitHub Actions, Robolectric API 34, synthetic/public fixtures, no physical phone',
              'commit':os.environ['GITHUB_SHA'],
              'run_url':f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"}
    (output/'verification-android.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    (output/'SHA256SUMS-android.txt').write_text(f'{digest}  {target.name}\n',encoding='utf-8',newline='\n')
    print(json.dumps({'apk':target.name,'version':version,'application_id':metadata[1],'tests':counts,'sha256':digest}))


if __name__ == '__main__':
    main()
