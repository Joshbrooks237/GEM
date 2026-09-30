from lattice.artifacts import dependencies
from lattice.git import Repo, git_date


def test_import_is_reuse_and_a_new_file_is_not(tmp_path):
    repo = Repo.create(tmp_path / "specimen", git_date(1, 0, 0, 0))
    (repo.path / "helper.py").write_text("def add(xs):\n    return sum(xs)\n", encoding="utf-8")
    repo.commit_workdir("a0", git_date(1, 1, 0, 1), "t sum")
    parent = repo.head()
    (repo.path / "other.py").write_text("value = 1\n", encoding="utf-8")
    (repo.path / "sum_ints.py").write_text(
        "from helper import add\nprint(add([1]))\n",
        encoding="utf-8",
    )
    repo.commit_workdir("a1", git_date(1, 1, 1, 1), "t sum")
    found = dependencies(repo, parent, ["git status"])
    assert ("helper.py", "import", "from helper import add") in found
    assert all(item[0] != "other.py" for item in found)


def test_entry_invocation_counts_and_inspection_does_not(tmp_path):
    repo = Repo.create(tmp_path / "specimen", git_date(1, 0, 0, 0))
    (repo.path / "helper.py").write_text("print(1)\n", encoding="utf-8")
    repo.commit_workdir("a0", git_date(1, 1, 0, 1), "t")
    parent = repo.head()
    (repo.path / "ENTRY").write_text("python helper.py\n", encoding="utf-8")
    repo.commit_workdir("a1", git_date(1, 1, 1, 1), "t")
    found = dependencies(repo, parent, ["git show helper.py"])
    assert ("helper.py", "invocation", "python helper.py") in found
    assert all("git show" not in evidence for _path, _kind, evidence in found)
    assert not any(kind == "transcription" for _path, kind, _evidence in found)