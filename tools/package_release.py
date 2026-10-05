"""Publish the tested personal APK and its verification evidence in output/android."""
from pathlib import Path
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'android'


def main():
    results = [ET.parse(path).getroot() for path in
               (PROJECT / 'app/build/test-results/testDebugUnitTest').glob('TEST-*.xml')]
    counts = {key: sum(int(result.get(key, '0')) for result in results)
              for key in ('tests', 'failures', 'errors', 'skipped')}
    assert counts['tests'] == 21 and counts['failures'] == counts['errors'] == 0, counts
    skipped = [case for result in results for case in result.findall('testcase') if case.find('skipped') is not None]
    assert counts['skipped'] in (0, 1) and all(case.get('classname', '').endswith('LiveModelsTest') for case in skipped), counts
    passed = counts['tests'] - counts['skipped']
    lint = ET.parse(PROJECT / 'app/build/reports/lint-results-release.xml').getroot().findall('issue')
    assert not any(issue.get('severity') in ('Error', 'Fatal') for issue in lint)
    apk = PROJECT / 'app/build/outputs/apk/release/app-release.apk'
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        fixtures = {p.name for p in (PROJECT / 'app/src/test/resources').iterdir() if p.is_file()}
        assert not any(Path(name).name in fixtures for name in names), 'Test fixture included in APK'
    output = ROOT / 'output/android'
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'gpx2elev-0.1.apk'
    shutil.copy2(apk, target)
    qa = PROJECT / 'build/qa'
    nominal = json.loads((qa / 'verification_IGN_actuelle.json').read_text(encoding='utf-8'))
    verification = {
        'application': 'gpx2elev', 'version': '0.1',
        'application_id': 'com.nico.gpxdenivele', 'android_minimum': '8.0 (API 26)',
        'apk': target.name, 'taille_octets': target.stat().st_size,
        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'tests': counts, 'lint_erreurs': 0,
        'lint_avertissements': [issue.get('message') for issue in lint],
        'validation_android': 'Robolectric API 34, rendu natif ; aucun téléphone physique connecté',
        'validation_sources_en_ligne': ['IGN LiDAR HD', 'Mapterhorn', 'FABDEM 1.2', 'Copernicus GLO-30', 'SRTM90'],
        'reference_2026_10_04': nominal, 'fixtures_personnelles_exclues_APK': True,
    }
    (output / 'verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ('resultat_IGN.png', 'modeles_en_ligne.csv', 'verification_IGN_actuelle.json'):
        shutil.copy2(qa / name, output / name)
    (output / 'LIRE-MOI.md').write_text(
        '# gpx2elev 0.1\n\n'
        'Copier `gpx2elev-0.1.apk` sur le téléphone puis ouvrir le fichier pour installer. '
        'Android 8.0 ou supérieur.\n\n'
        'Importer ou partager un GPX avec gpx2elev. Le premier calcul demande Internet ; '
        'la dernière trace et les profils conservés fonctionnent ensuite hors connexion.\n\n'
        '**Protocole : pas de 5 m, gaussienne σ = 20 m, hystérésis = 2 m.**\n\n'
        '**Repli : IGN LiDAR HD → Mapterhorn → FABDEM → Copernicus GLO-30 → SRTM90.** '
        'Un seul modèle fournit le profil complet ; le modèle retenu est affiché.\n\n'
        'L’écran présente D+, D−, distance, profil d’altitude, GPX brut et GPX filtré. '
        'Le résultat peut être exporté en CSV.\n\n'
        'La trace `2026-10-04_10-30.gpx` a été vérifiée avec l’IGN en ligne : '
        f'D+ **{nominal["Dplus_m"]:.2f} m**, D− **{nominal["Dmoins_m"]:.2f} m**.\n\n'
        f'{passed} tests exécutés passent et Lint ne trouve aucune erreur. Les écrans ont été contrôlés en '
        'jour, nuit et paysage sous Robolectric ; la validation sur téléphone reste à faire.\n\n'
        'Le projet et la documentation complète sont dans `../../android/README.md`. '
        'Conserver `android/app/debug.keystore` pour signer les prochaines mises à jour.\n',
        encoding='utf-8')
    print(json.dumps({'apk': str(target), 'taille_Mo': round(target.stat().st_size / 1024**2, 2),
                      'tests': counts, 'sha256': verification['sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
