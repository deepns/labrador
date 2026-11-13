"""The answer benchmark's fictional documents: qa.jsonl rows are well formed and the passport MRZ is valid."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "bench"))
make_bench = pytest.importorskip("make_bench")  # needs pillow, numpy, reportlab only for the documents


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("bench")
    make_bench.QA.clear()
    make_bench.build_documents(root)
    rows = [json.loads(json.dumps(r)) for r in make_bench.QA]  # must be JSON-serialisable
    return root, rows


def test_qa_rows_are_well_formed(built):
    root, rows = built
    assert 20 <= len(rows) <= 40
    cats = {r["category"] for r in rows}
    assert cats == {"id-lookup", "date", "missing", "near-miss", "conflict", "misleading"}
    for r in rows:
        expect = [r["expect"]] if isinstance(r["expect"], str) else r["expect"]
        assert all((root / e).exists() for e in expect), r
        assert isinstance(r["answerable"], bool)
        assert bool(r["answer"]) == r["answerable"], r
        if r["answer"].startswith("re:"):
            re.compile(r["answer"][3:])
        near = [r["near"]] if isinstance(r.get("near"), str) else r.get("near", [])
        assert all((root / e).exists() for e in near), r
        assert (r["category"] == "near-miss") == bool(near), r
        if not r["answerable"]:
            assert r["expect"] == [], r
        for b in r.get("bad", []):
            if b.startswith("re:"):
                re.compile(b[3:])
    assert len({r["question"] for r in rows}) == len(rows)


def test_passport_mrz_check_digits(built):
    root, _ = built
    # pypdfium2 runs in a child: loading it in the pytest process makes later subprocess forks segfault on macOS
    code = "import sys, pypdfium2 as p; print(p.PdfDocument(sys.argv[1])[0].get_textpage().get_text_range())"
    text = subprocess.run([sys.executable, "-c", code, str(root / "documents/old-passport.pdf")],
                          capture_output=True, text=True, check=True).stdout
    (old,) = [ln.strip() for ln in text.splitlines() if len(ln.strip()) == 44 and ln.strip().startswith("KB2206937")]
    assert "09 JUN 2014" in text and old[21:27] == "140609"
    # the current passport is an image, so check the generator's function for it; the old one is read back above
    cur = make_bench.td3("HALVORSEN", "TOVE MARIE", "QX7340518", "880314", "F", "330402")[1]
    for l2 in (old, cur):
        assert len(l2) == 44
        assert l2[9] == make_bench.mrz_check(l2[:9]) and l2[19] == make_bench.mrz_check(l2[13:19])
        assert l2[27] == make_bench.mrz_check(l2[21:27]) and l2[42] == make_bench.mrz_check(l2[28:42])
        assert l2[43] == make_bench.mrz_check(l2[0:10] + l2[13:20] + l2[21:43])


def test_date_re():
    pat = re.compile(make_bench.date_re(2033, 4, 2)[3:])
    for ok in ["02 APR 2033", "2 April 2033", "2033-04-02", "Apr 2, 2033", "April 02 2033"]:
        assert pat.search(ok), ok
    for bad in ["12 April 2033", "22 Apr 2033", "2 April 20331", "12033-04-02"]:
        assert not pat.search(bad), bad


def test_icao_specimen_check_digits():
    # ICAO 9303 specimen: L898902C3 -> 6, dob 740812 -> 2, expiry 120415 -> 9
    assert (make_bench.mrz_check("L898902C3"), make_bench.mrz_check("740812"), make_bench.mrz_check("120415")) == ("6", "2", "9")
