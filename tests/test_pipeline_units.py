"""Fragment-level tests for the pipeline helper functions."""

from src.pipeline import (
    PipelineConfig,
    _build_gen_config,
    _content_hash,
    _detect_multi_pbip_folders,
    _find_pbip_files,
    _get_output_path,
)


def test_find_pbip_files_recursive(tmp_path):
    (tmp_path / "A.pbip").write_text("", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "B.pbip").write_text("", encoding="utf-8")
    (sub / "not.txt").write_text("", encoding="utf-8")
    files = _find_pbip_files(str(tmp_path))
    assert len(files) == 2
    assert all(f.endswith(".pbip") for f in files)


def test_find_pbip_files_empty(tmp_path):
    assert _find_pbip_files(str(tmp_path)) == []


def test_detect_multi_pbip_folders():
    files = [r"C:\a\one.pbip", r"C:\a\two.pbip", r"C:\b\three.pbip"]
    skipped, runnable = _detect_multi_pbip_folders(files)
    assert skipped == {r"C:\a"}
    assert runnable == [r"C:\b\three.pbip"]


def test_detect_multi_pbip_folders_all_unique():
    files = [r"C:\a\one.pbip", r"C:\b\two.pbip"]
    skipped, runnable = _detect_multi_pbip_folders(files)
    assert skipped == set()
    assert runnable == files


def test_get_output_path_md_next_to_pbip():
    assert _get_output_path(r"C:\rep", "Sales", "md", "") == r"C:\rep\README.md"


def test_get_output_path_html_custom_folder():
    assert _get_output_path(r"C:\rep", "Sales", "html", r"C:\docs") == r"C:\docs\Sales\Sales.html"


def test_build_gen_config():
    cfg = PipelineConfig(
        reports_folder="x", owner="O", team="T", refresh_schedule="R", include_dax=False
    )
    gen = _build_gen_config("Sales", cfg)
    assert gen == {
        "report_name":      "Sales",
        "owner":            "O",
        "team":             "T",
        "refresh_schedule": "R",
        "include_dax":      False,
    }


def test_content_hash_deterministic(tmp_path):
    model = tmp_path / "Sales.SemanticModel"
    model.mkdir()
    (model / "a.tmdl").write_text("A", encoding="utf-8")
    (model / "b.tmdl").write_text("B", encoding="utf-8")
    cfg = PipelineConfig(reports_folder="")
    h1 = _content_hash(str(model), cfg)
    h2 = _content_hash(str(model), cfg)
    assert h1 == h2
    assert len(h1) == 64


def test_content_hash_changes_with_content(tmp_path):
    model = tmp_path / "Sales.SemanticModel"
    model.mkdir()
    (model / "a.tmdl").write_text("A", encoding="utf-8")
    cfg = PipelineConfig(reports_folder="")
    before = _content_hash(str(model), cfg)
    (model / "a.tmdl").write_text("B", encoding="utf-8")
    after = _content_hash(str(model), cfg)
    assert before != after


def test_content_hash_changes_with_config(tmp_path):
    model = tmp_path / "Sales.SemanticModel"
    model.mkdir()
    (model / "a.tmdl").write_text("A", encoding="utf-8")
    c1 = PipelineConfig(reports_folder="", include_dax=True)
    c2 = PipelineConfig(reports_folder="", include_dax=False)
    assert _content_hash(str(model), c1) != _content_hash(str(model), c2)
