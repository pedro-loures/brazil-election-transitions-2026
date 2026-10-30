import zipfile

import numpy as np
import pandas as pd
import pytest

from elections.data import prepare


def write_archive(folder, stem, frame):
    with zipfile.ZipFile(folder / f"{stem}_2026.zip", "w") as z:
        z.writestr(f"{stem}_2026_BR.csv", frame.to_csv(index=False, sep=";").encode("latin1"))
        # Consolidated copies must never be added a second time.
        z.writestr(f"{stem}_2026_BRASIL.csv", frame.to_csv(index=False, sep=";").encode("latin1"))


def fixture_archives(raw):
    detail, votes, reference, registry = [], [], [], []
    rng = np.random.default_rng(77)
    for section in range(1, 13):
        x = rng.integers(10, 80, 5)
        technical = section % 2
        n = int(x.sum())
        y = rng.multinomial(n, [.4, .35, .05, .2])
        for turn, counts in [(1, x), (2, np.array([y[0], y[1], 0, y[2], y[3]]))]:
            a, b, other, invalid, absent = map(int, counts)
            common = {"ANO_ELEICAO": 2026, "CD_TIPO_ELEICAO": 2, "CD_CARGO": 1,
                      "CD_ELEICAO": 6256+turn, "SG_UF": "SC", "CD_MUNICIPIO": 81914,
                      "NM_MUNICIPIO": "LEBON RÉGIS", "NR_ZONA": 77, "NR_TURNO": turn}
            tech = technical if turn == 1 else 0
            # Invalid ballot number 28 is represented among nominal votes in
            # the section source, but as technical-null in official totals.
            blank, null = invalid//2, invalid-invalid//2-tech
            detail.append({**common, "NR_SECAO": section, "NR_LOCAL_VOTACAO": 1001,
                "QT_APTOS": n, "QT_COMPARECIMENTO": n-absent, "QT_ABSTENCOES": absent,
                "QT_VOTOS_BRANCOS": blank, "QT_VOTOS_NULOS": null,
                "QT_VOTOS_NOMINAIS": a+b+other+tech,
                "ST_SECAO_INSTALADA": "Sim", "ST_SECAO_ANULADA": "Não"})
            for number, name, quantity in [(13, "A", a), (22, "B", b), (55, "C", other),
                                            (28, "Unregistered", tech), (95, "Blank", blank), (96, "Null", null)]:
                if quantity:
                    votes.append({**common, "NR_SECAO": section, "NR_VOTAVEL": number,
                                  "NM_VOTAVEL": name, "QT_VOTOS": quantity})
            reference.append({**common, "QT_APTOS": n, "QT_COMPARECIMENTO": n-absent,
                "QT_ABSTENCOES": absent, "QT_VOTOS_BRANCOS": blank,
                "QT_TOTAL_VOTOS_NULOS": null+tech, "QT_TOTAL_VOTOS_VALIDOS": a+b+other,
                "QT_SECOES_PRINCIPAIS": 1, "QT_VOTOS_NULOS_TECNICOS": tech})
            for number, name, quantity in [(13, "A", a), (22, "B", b), (55, "C", other)]:
                registry.append({**common, "NR_CANDIDATO": number, "NM_CANDIDATO": name,
                    "NM_TIPO_DESTINACAO_VOTOS": "Válido", "QT_VOTOS_NOMINAIS": quantity,
                    "QT_VOTOS_NOMINAIS_VALIDOS": quantity})
    write_archive(raw, "detalhe_votacao_secao", pd.DataFrame(detail))
    # The candidate vote archive has _BR in its ZIP name as well as the CSV.
    with zipfile.ZipFile(raw / "votacao_secao_2026_BR.zip", "w") as z:
        z.writestr("votacao_secao_2026_BR.csv", pd.DataFrame(votes).to_csv(index=False, sep=";").encode("latin1"))
    write_archive(raw, "detalhe_votacao_munzona", pd.DataFrame(reference))
    write_archive(raw, "votacao_candidato_munzona", pd.DataFrame(registry))


def test_ingestion_reconciles_technical_nulls_without_double_counting(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    fixture_archives(raw)
    output = tmp_path / "processed"
    meta = prepare(raw, output, 2026)
    d = pd.read_csv(output / "section_rounds.csv.gz")
    ref = pd.read_csv(output / "municipal_reference.csv")
    assert meta["section_rounds"] == 24
    assert d.section_usable.all()
    assert d.technical_null.sum() == 6
    assert d.valid.sum() == ref.valid.sum()
    assert d["null"].sum() == ref["null"].sum()
    candidates = pd.read_csv(output / "candidates.csv")
    assert not candidates.loc[candidates.candidate_number.eq(28), "registered_valid_candidate"].any()


def test_unknown_code_cannot_be_silently_reclassified_without_reference_match(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    fixture_archives(raw)
    path = raw / "detalhe_votacao_munzona_2026.zip"
    with zipfile.ZipFile(path) as z:
        frame = pd.read_csv(z.open("detalhe_votacao_munzona_2026_BR.csv"), sep=";", encoding="latin1")
    frame["QT_VOTOS_NULOS_TECNICOS"] = 0
    write_archive(raw, "detalhe_votacao_munzona", frame)
    with pytest.raises(ValueError, match="technical-null totals"):
        prepare(raw, tmp_path / "processed", 2026)


def test_end_to_end_analysis_exports_reconciled_counts_and_flow_margins(tmp_path, monkeypatch):
    from elections.analysis import analyze
    import json
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    raw = tmp_path / "raw"; raw.mkdir()
    fixture_archives(raw)
    processed, output = tmp_path / "processed", tmp_path / "results"
    prepare(raw, processed, 2026)
    result = analyze(processed, output, bootstrap=3, workers=1)
    assert result["municipalities"] == 1
    cities = pd.read_csv(output / "municipalities.csv")
    assert cities.reference_all_totals_match.all()
    assert cities.iloc[0].electorate_coverage == 1
    assert cities.iloc[0].model_status == "ok"
    flows = pd.read_csv(output / "estimated_flows.csv.gz")
    full = flows[flows.model.eq("full")]
    for label in ["a", "b"]:
        total = full.loc[full.destination.eq(label), "estimated_voters"].sum()
        assert total == pytest.approx(cities.iloc[0][f"{label}_2"], abs=1e-4)
    assert (output / "report.html").is_file()
    assert json.loads((output / "summary.json").read_text())["logs_status"] == "not_loaded"
