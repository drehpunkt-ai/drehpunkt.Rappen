# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml==6.0.3"]
# ///
"""Prüft mit Trivy alle Images aus den Compose-Dateien des Repos (per Digest, auch die eigenen aus der Registry von
GitHub) und das Repo selbst: Abhängigkeiten in den Lockfiles, Dockerfiles und Infrastruktur-Code (ARCHITEKTUR.md,
Kapitel 9, Lieferkette). Läuft wöchentlich als GitHub Action (.github/workflows/trivy.yml) und von Hand.

Dieselbe Datei steht in jedem Repo mit Code. Das Original liegt in drehpunkt.Plattform, Änderungen dort und danach
in die anderen Repos kopieren.

Kritisch heisst Stufe CRITICAL mit verfügbarer Korrektur: Dann endet das Skript mit 1. HIGH mit Korrektur steht als
Hinweis im Bericht. Bewusst hingenommene Funde stehen in .trivyignore.yaml, mit Begründung (statement) und
Ablaufdatum (expired_at). Ein Image, das sich nicht prüfen lässt, gilt ebenfalls als Fehler.

Das Ergebnis steht in trivy-ergebnis.json (für den Versions-Exporter, Kapitel 8) und als Bericht in der Ausgabe, in
GitHub Actions zusätzlich in der Zusammenfassung des Laufs.

Aufruf: uv run --offline --script werkzeuge/trivy-pruefen.py [--trivy <pfad>]
"""
import datetime
import json
import os
import subprocess
import sys

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IGNORIEREN = os.path.join(REPO, ".trivyignore.yaml")
# Eigene Images laufen über zot (registry.drehpunkt.cloud, nur im Tailnet), das sie von GitHub holt
UMSCHREIBEN = {"registry.drehpunkt.cloud/": "ghcr.io/"}
UMGEBUNG = dict(os.environ, TRIVY_SKIP_VERSION_CHECK="true", TRIVY_DISABLE_TELEMETRY="true", TRIVY_NO_PROGRESS="true")


def compose_dateien():
    r = subprocess.run(["git", "-C", REPO, "ls-files", "*compose.yaml"], check=True, capture_output=True, text=True)
    return sorted(r.stdout.split())


def images():
    aus = {}
    for datei in compose_dateien():
        with open(os.path.join(REPO, datei)) as f:
            inhalt = yaml.safe_load(f) or {}
        for dienst in (inhalt.get("services") or {}).values():
            bild = (dienst or {}).get("image")
            if bild:
                aus.setdefault(bild, set()).add(datei)
    return {b: sorted(d) for b, d in sorted(aus.items())}


def trivy(programm, *argumente):
    befehl = [programm, *argumente, "--quiet", "--format", "json"]
    if os.path.exists(IGNORIEREN):
        befehl += ["--ignorefile", IGNORIEREN]
    r = subprocess.run(befehl, capture_output=True, text=True, env=UMGEBUNG, timeout=900)
    if r.returncode != 0:
        return None, (r.stderr.strip().splitlines() or ["ohne Meldung"])[-1][:300]
    return json.loads(r.stdout or "{}"), ""


def funde_images(bericht):
    """Ein Fund pro Lücke, die betroffenen Pakete zusammengefasst."""
    funde = {}
    for ziel in bericht.get("Results") or []:
        for v in ziel.get("Vulnerabilities") or []:
            if not v.get("FixedVersion"):
                continue
            f = funde.setdefault(v["VulnerabilityID"], {
                "stufe": v["Severity"], "id": v["VulnerabilityID"], "pakete": [], "behoben_in": v["FixedVersion"],
                "titel": (v.get("Title") or "")[:120]})
            paket = f"{v.get('PkgName')} {v.get('InstalledVersion')}"
            if paket not in f["pakete"]:
                f["pakete"].append(paket)
    return list(funde.values())


def funde_repo(bericht):
    """Lücken in Abhängigkeiten (mit Korrektur) und Fehlkonfigurationen, je mit der Datei."""
    funde = []
    for ziel in bericht.get("Results") or []:
        for f in funde_images({"Results": [ziel]}):
            funde.append({**f, "datei": ziel.get("Target")})
        for m in ziel.get("Misconfigurations") or []:
            if m.get("Status") == "FAIL":
                funde.append({"stufe": m["Severity"], "id": m.get("AVDID") or m.get("ID"), "datei": ziel.get("Target"),
                              "titel": (m.get("Title") or "")[:120]})
    return funde


def main():
    programm = sys.argv[sys.argv.index("--trivy") + 1] if "--trivy" in sys.argv else "trivy"
    ergebnis = {"zeit": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"), "images": [], "ungepinnt": [], "repo": {}}
    for bild, dateien in images().items():
        if "@sha256:" not in bild:
            # Lokal gebaut oder nicht gepinnt: Trivy kann es nicht holen. Dockerfile und Lockfiles prüft der Teil «Repo»
            ergebnis["ungepinnt"].append({"image": bild, "dateien": dateien})
            print(f"HINWEIS {bild}: ohne Digest, nicht geprüft", flush=True)
            continue
        ziel = bild
        for alt, neu in UMSCHREIBEN.items():
            if ziel.startswith(alt):
                ziel = neu + ziel.removeprefix(alt)
        bericht, fehler = trivy(programm, "image", "--scanners", "vuln", "--severity", "HIGH,CRITICAL",
                                "--ignore-unfixed", ziel)
        eintrag = {"image": bild, "dateien": dateien, "fehler": fehler, "funde": funde_images(bericht) if bericht else []}
        ergebnis["images"].append(eintrag)
        kritisch = sum(f["stufe"] == "CRITICAL" for f in eintrag["funde"])
        print(f"{'FEHLER ' if fehler else ''}{bild.split('@')[0]}: {kritisch} kritisch, "
              f"{len(eintrag['funde']) - kritisch} hoch" + (f" ({fehler})" if fehler else ""), flush=True)
    bericht, fehler = trivy(programm, "fs", "--scanners", "vuln,misconfig", "--severity", "HIGH,CRITICAL",
                            "--ignore-unfixed", "--skip-dirs", "node_modules", REPO)
    ergebnis["repo"] = {"fehler": fehler, "funde": funde_repo(bericht) if bericht else []}
    print(f"Repo: {sum(f['stufe'] == 'CRITICAL' for f in ergebnis['repo']['funde'])} kritisch, "
          f"{sum(f['stufe'] == 'HIGH' for f in ergebnis['repo']['funde'])} hoch" + (f" ({fehler})" if fehler else ""))

    with open(os.path.join(REPO, "trivy-ergebnis.json"), "w") as f:
        json.dump(ergebnis, f, indent=2, ensure_ascii=False)

    kritisch = [(e["image"], f) for e in ergebnis["images"] for f in e["funde"] if f["stufe"] == "CRITICAL"]
    kritisch += [(f["datei"], f) for f in ergebnis["repo"]["funde"] if f["stufe"] == "CRITICAL"]
    hoch = sum(f["stufe"] == "HIGH" for e in ergebnis["images"] for f in e["funde"])
    hoch += sum(f["stufe"] == "HIGH" for f in ergebnis["repo"]["funde"])
    fehler = [(e["image"], e["fehler"]) for e in ergebnis["images"] if e["fehler"]]
    if ergebnis["repo"]["fehler"]:
        fehler.append(("Repo", ergebnis["repo"]["fehler"]))

    zeilen = [f"## Trivy, {ergebnis['zeit']}", "",
              f"{len(ergebnis['images'])} Images und das Repo, {len(kritisch)} kritische Funde mit Korrektur, {hoch} hohe, "
              f"{len(fehler)} nicht prüfbar", ""]
    if kritisch:
        zeilen += ["### Kritisch", "", "| Ziel | Fund | Paket | behoben in |", "|---|---|---|---|"]
        zeilen += [f"| `{z.split('@')[0]}` | {f['id']} {f['titel']} | {', '.join(f.get('pakete') or [f.get('datei')])} "
                   f"| {f.get('behoben_in') or ''} |" for z, f in kritisch]
        zeilen.append("")
    if ergebnis["ungepinnt"]:
        zeilen += ["### Ohne Digest, nicht geprüft", ""]
        zeilen += [f"- `{e['image']}` in {', '.join(e['dateien'])}" for e in ergebnis["ungepinnt"]] + [""]
    if fehler:
        zeilen += ["### Nicht prüfbar", ""] + [f"- `{z.split('@')[0]}`: {t}" for z, t in fehler] + [""]
    hohe_repo = [f for f in ergebnis["repo"]["funde"] if f["stufe"] == "HIGH"]
    if hohe_repo:
        zeilen += ["### Hoch im Repo (Abhängigkeiten, Dockerfiles, Infrastruktur-Code)", ""]
        zeilen += [f"- {f['id']} in `{f['datei']}`: {f['titel']}" + (f" (behoben in {f['behoben_in']})"
                   if f.get("behoben_in") else "") for f in hohe_repo]
        zeilen.append("")
    text = "\n".join(zeilen)
    print("\n" + text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text + "\n")
    sys.exit(1 if kritisch or fehler else 0)


if __name__ == "__main__":
    main()
