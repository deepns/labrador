"""The answer benchmark's fictional documents: qa.jsonl rows are well formed and the passport MRZ is valid."""

import json
import re
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


def check_digit(s):  # ICAO 9303: weights 7,3,1; digits as is, A-Z = 10..35, '<' = 0
    val = lambda c: int(c) if c.isdigit() else 0 if c == "<" else ord(c) - 55
    return str(sum(val(c) * (7, 3, 1)[i % 3] for i, c in enumerate(s)) % 10)


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
    assert len({r["question"] for r in rows}) == len(rows)


def test_passport_mrz_check_digits(built):
    # the old passport's text layer is a PDF; check the generator's output for both via the function it uses
    for args in [("HALVORSEN", "TOVE MARIE", "QX7340518", "880314", "F", "330402"),
                 ("HALVORSEN", "TOVE MARIE", "KB2206937", "880314", "F", "140609")]:
        l1, l2 = make_bench.td3(*args)
        assert len(l1) == len(l2) == 44 and l1.startswith("P<UTO")
        assert l2[9] == check_digit(l2[:9]) and l2[19] == check_digit(l2[13:19]) and l2[27] == check_digit(l2[21:27])
        assert l2[42] == check_digit(l2[28:42]) and l2[43] == check_digit(l2[0:10] + l2[13:20] + l2[21:43])


def test_icao_specimen_check_digits():
    # ICAO 9303 specimen: L898902C3 -> 6, dob 740812 -> 2, expiry 120415 -> 9
    assert (check_digit("L898902C3"), check_digit("740812"), check_digit("120415")) == ("6", "2", "9")
