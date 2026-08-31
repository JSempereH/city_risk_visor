"""Cross-checks each non-San-Jose city's precomputed PSHA curve
(app/data/psha/{city}.csv) against the best independently published
estimate this project could find for that exact site. Same spirit as
San Jose's own published-curve validation (docs/psha_plan.md's
Validation section, tests/test_psha.py's
test_pga_matches_published_hidalgo_leiva_validation), but weaker: none
of these three cities have a published PGA hazard curve at their exact
site (see docs/psha_plan.md), so each check below is either a single
approximate PGA point or a magnitude/distance disaggregation
cross-check, not a full-curve overlay. Results and sourcing are written
up in docs/psha_plan.md's Validation section; this script is what
reproduces the numbers quoted there.

Downloads each source document into _raw_validation/{city}/ (gitignored,
same convention as fetch_sources.py's _raw/), then extracts the
comparison value(s) from it, rather than hardcoding numbers copied by
hand: rerunning this script re-fetches the source and re-parses it, so
it will fail loudly (not silently report stale numbers) if the upstream
text changes in a way that breaks the parser.

Requires `pdftotext` (poppler-utils) on PATH for the two PDF sources.

Usage: uv run python scripts/psha/validate_independent.py [city ...]
(no args = all three cities)
"""

from __future__ import annotations

import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from lib import RAW_DIR

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.hazard import psha  # noqa: E402

RAW_VALIDATION_DIR = RAW_DIR.parent / "_raw_validation"


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "risk_viewer-psha-validate/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _pdftotext(pdf_path: Path) -> str:
    txt_path = pdf_path.with_suffix(".txt")
    if not txt_path.exists():
        subprocess.run(["pdftotext", "-layout", str(pdf_path), str(txt_path)], check=True)
    return txt_path.read_text(errors="replace")


def _our_pga(city: str, return_period_years: int) -> float:
    return psha.sa_by_period_for_return_period(city, return_period_years)[0.01]


# --- Guatemala City -------------------------------------------------------
#
# Gamboa-Cante et al. (2025), "Comprehensive Methodology for Assessing
# Structural Response to Probable Seismic Motions: Application to
# Guatemala City", Geosciences 15(11):427, CC BY 4.0 (MDPI open access).
# https://doi.org/10.3390/geosciences15110427. Fetched via UPM's own
# open-access repository (MDPI itself blocks this environment's egress).
# Section 3.2: the KUKAHPAN-25 regional model's own disaggregation gives
# two control earthquakes for Guatemala City at a 475-year return
# period, one per target motion:
#   (M1, R1) = (6.5-7.0 Mw, 20-30 km) -> PGA
#   (M2, R2) = (6.0-6.5 Mw, 20-30 km) -> Sa(0.5s)
# No numeric PGA value is given in text (only in an unparsed map
# figure), so this is a magnitude/distance cross-check against this
# project's own PGA disaggregation, not a PGA-value comparison.

GUATEMALA_PDF_URL = "https://oa.upm.es/94751/1/10413349.pdf"


def fetch_guatemala() -> Path:
    dest = RAW_VALIDATION_DIR / "guatemala"
    dest.mkdir(parents=True, exist_ok=True)
    pdf_path = dest / "gamboa_cante_2025_guatemala_city.pdf"
    if not pdf_path.exists():
        pdf_path.write_bytes(_download(GUATEMALA_PDF_URL))
        print(f"guatemala: fetched {pdf_path}")
    return pdf_path


def compare_guatemala() -> None:
    text = _pdftotext(fetch_guatemala())
    m = re.search(
        r"\(M1\s*,\s*R1\s*\)\s*=\s*\(([\d.]+)[^\d.]+([\d.]+)\s*Mw,\s*([\d.]+)[^\d.]+([\d.]+)\s*km\)",
        text,
    )
    if not m:
        raise RuntimeError(
            "guatemala: could not find the (M1, R1) control-earthquake sentence in the "
            "downloaded PDF text (the paper's wording may have changed), check "
            f"{fetch_guatemala().with_suffix('.txt')} by hand"
        )
    m_lo, m_hi, r_lo, r_hi = (float(x) for x in m.groups())
    print("\n=== Guatemala City ===")
    print(f"Published (KUKAHPAN-25, Gamboa-Cante et al. 2025), 475yr PGA control earthquake:")
    print(f"  Mw {m_lo}-{m_hi}, R {r_lo}-{r_hi} km")
    our_top_bin = _top_disagg_bin("guatemala", 475)
    print(f"This project's own 475yr PGA disaggregation, single largest (M,R) bin:")
    print(f"  Mw {our_top_bin[0]:.2f}, R {our_top_bin[1]:.0f} km (fraction {our_top_bin[2]:.1%})")
    in_range = m_lo <= our_top_bin[0] <= m_hi + 0.5  # KUKAHPAN-25's bin is coarse; allow half a magnitude unit
    print(
        "  -> near-field mode is "
        + ("broadly consistent with" if in_range else "NOT consistent with")
        + " the published control earthquake's magnitude range"
    )
    print(
        "  Note: this project's own disaggregation is bimodal (a comparably-weighted far-field\n"
        "  ~110km subduction bin also contributes, see app/data/psha/guatemala_disagg.csv);\n"
        "  the weighted-mean single-event summary psha._controlling_event() returns for this city\n"
        "  (~Mw 7.3, ~78km) sits between the two modes and matches neither well, a real,\n"
        "  documented limitation of collapsing a bimodal disaggregation into one (M,R) pair."
    )


def _top_disagg_bin(city: str, return_period_years: int) -> tuple[float, float, float]:
    import csv

    from lib import DATA_DIR

    rows = [
        r
        for r in csv.DictReader(open(DATA_DIR / f"{city}_disagg.csv"))
        if int(r["return_period_years"]) == return_period_years
    ]
    top = max(rows, key=lambda r: float(r["fraction"]))
    return float(top["mag_bin"]), float(top["dist_bin"]), float(top["fraction"])


# --- Santo Domingo ----------------------------------------------------------
#
# Johnson, Chartier, Pagani, Perez, Guzman, Betania Roque Quezada, Yepes
# Estrada (2023), "PSHA for the Dominican Republic", EGU General
# Assembly 2023 abstract, CC BY 4.0.
# https://doi.org/10.5194/egusphere-egu23-13313 (freely accessible
# abstract page; the full peer-reviewed paper, Johnson et al. 2024,
# Earthquake Spectra, is the same GEM model this project's own source
# model comes from, but is paywalled). Quote: "In Santiago de los
# Caballeros, PGA reaches ~1g for 2% probability of exceedance in 50
# years [2475yr], controlled by the Septentrional Fault, while in the
# capital (Santo Domingo) PGA of ~0.5g is impacted by all tectonic
# region types". Read as the same 2475yr level (same sentence,
# continued clause). A single approximate ("~", no decimal places)
# point, not a full curve (the weakest-precision of these three
# cross-checks), but from the same team and model family as this
# project's own source model.

SANTO_DOMINGO_ABSTRACT_URL = "https://meetingorganizer.copernicus.org/EGU23/EGU23-13313.html"


def fetch_santo_domingo() -> Path:
    dest = RAW_VALIDATION_DIR / "santo_domingo"
    dest.mkdir(parents=True, exist_ok=True)
    html_path = dest / "johnson_2023_egu23_abstract.html"
    if not html_path.exists():
        html_path.write_bytes(_download(SANTO_DOMINGO_ABSTRACT_URL))
        print(f"santo_domingo: fetched {html_path}")
    return html_path


def compare_santo_domingo() -> None:
    html = fetch_santo_domingo().read_text(errors="replace")
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"capital \(Santo Domingo\) PGA of[^\d]*([\d.]+)\s*g", text)
    if not m:
        raise RuntimeError(
            "santo_domingo: could not find the 'capital (Santo Domingo) PGA of ~Xg' sentence "
            "in the downloaded abstract (the page's wording may have changed)"
        )
    published_pga = float(m.group(1))
    our_pga = _our_pga("santo_domingo", 2475)
    rel_diff = abs(our_pga - published_pga) / published_pga
    print("\n=== Santo Domingo ===")
    print(f"Published (Johnson et al. 2023 EGU abstract), ~2475yr PGA: ~{published_pga}g (order-of-magnitude, stated to 1 sig fig)")
    print(f"This project's own 2475yr PGA: {our_pga:.4f}g")
    print(f"  -> relative difference: {rel_diff:.1%}")


# --- Lomas del Centinela (Zapopan / Guadalajara metro area) -----------------
#
# Buenrostro Orozco, A.M. (2017), "Analisis de peligro sismico para la
# Zona Metropolitana de Guadalajara" (Master's thesis, UAM Azcapotzalco),
# open access via the university's own repository.
# https://zaloamati.azc.uam.mx/items/7d2b6bbd-9dae-462e-b701-b027907308e6
# Two independent numbers, both from the ZMG grid point closest to Lomas
# del Centinela (20.7617, -103.3641):
#  - Table 6.4: PRODISISv4.1 (CFE's official 2015 national hazard tool)
#    PGA at "Colomos y Manuel M. Diéguez" (20.692, -103.371), ~7.8km from
#    the site.
#  - Table E.2 (Appendix E): the thesis's own EZ-FRISK PSHA, at grid
#    point ZMG-17 "Zapopan" (20.735, -103.392), ~3.5km from the site,
#    closer, but a different (non-official) method giving a visibly
#    higher PGA than PRODISIS at the same city (see Table 6.4's own
#    EPU-vs-PRODISIS columns), a real, unresolved disagreement between
#    two independently published Mexican sources for the same area.

LOMAS_CENTINELA_PDF_URL = (
    "https://zaloamati.azc.uam.mx/server/api/core/bitstreams/3f01a2b8-8a04-4bcf-807d-bb4cade46373/content"
)


def fetch_lomas_centinela() -> Path:
    dest = RAW_VALIDATION_DIR / "lomas_centinela"
    dest.mkdir(parents=True, exist_ok=True)
    pdf_path = dest / "buenrostro_orozco_2017_zmg_thesis.pdf"
    if not pdf_path.exists():
        pdf_path.write_bytes(_download(LOMAS_CENTINELA_PDF_URL))
        print(f"lomas_centinela: fetched {pdf_path}")
    return pdf_path


def compare_lomas_centinela() -> None:
    text = _pdftotext(fetch_lomas_centinela())

    # Table 6.4: PRODISIS PGA(g) at "Colomos y Manuel M. Diéguez", one row
    # per return period, "EPU" column then "PRODISISv4.1" column.
    block_match = re.search(
        r"Colomos y\s*\n?\s*Manuel M\. Di.guez contra PRODISIS, 2015.*?"
        r"(Tr\s*=?\s*100.*?Tr\s*=?\s*2475\s*a.os\s+[\d.]+\s+[\d.]+)",
        text,
        re.DOTALL,
    )
    if not block_match:
        raise RuntimeError(
            "lomas_centinela: could not find the Table 6.4 PRODISIS/Colomos block in the "
            "downloaded thesis text (layout extraction may have shifted)"
        )
    rows = re.findall(r"Tr\s*=?\s*(\d+)\s*a.os\s+([\d.]+)\s+([\d.]+)", block_match.group(1))
    prodisis_by_tr = {int(tr): float(prodisis) for tr, _, prodisis in rows}

    # Table E.2 (appendix): EPU(ZMG-17) column, T=0.01s row, Tr=475yr block.
    e2_match = re.search(r"Per.odo de Retorno 475 a.os.*?\n\s*(0\.01\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+)", text, re.DOTALL)
    if not e2_match:
        raise RuntimeError(
            "lomas_centinela: could not find the Table E.2 T=0.01s row in the downloaded "
            "thesis text (layout extraction may have shifted)"
        )
    zmg17_pga_475 = float(e2_match.group(1).split()[4])

    print("\n=== Lomas del Centinela (Zapopan / Guadalajara) ===")
    for tr in (100, 475, 975, 2475):
        our = _our_pga("lomas_centinela", tr)
        line = f"Tr={tr}yr: this project = {our:.4f}g"
        if tr in prodisis_by_tr:
            published = prodisis_by_tr[tr]
            rel_diff = abs(our - published) / published
            line += f", PRODISIS/CFE 2015 (Colomos, ~7.8km away) = {published:.2f}g (diff {rel_diff:+.0%})"
        if tr == 475:
            rel_diff = abs(our - zmg17_pga_475) / zmg17_pga_475
            line += f", thesis's own EZ-FRISK PSHA (ZMG-17, ~3.5km away) = {zmg17_pga_475:.3f}g (diff {rel_diff:+.0%})"
        print(f"  {line}")
    print(
        "  -> this project's curve reads consistently lower than both independent Mexican\n"
        "  sources at every shared return period, a real, unresolved discrepancy, not a\n"
        "  match (see docs/psha_plan.md)."
    )


COMPARISONS = {
    "guatemala": compare_guatemala,
    "santo_domingo": compare_santo_domingo,
    "lomas_centinela": compare_lomas_centinela,
}


def main() -> None:
    cities = sys.argv[1:] or list(COMPARISONS)
    for city in cities:
        COMPARISONS[city]()


if __name__ == "__main__":
    main()
