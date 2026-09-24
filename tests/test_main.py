"""The unified entry point must preserve phase order and fail fast."""

import pytest

import main


def test_pipeline_runs_modules_in_order(monkeypatch, capsys):
    called = []
    for _, name, module in main.STAGES:
        monkeypatch.setattr(module, "run", lambda name=name: called.append(name))
    main.run_pipeline()
    assert called == [name for _, name, _ in main.STAGES]
    output = capsys.readouterr().out
    assert output.count("PASS") == len(main.STAGES)
    assert output.endswith("Project pipeline completed successfully.\n")


def test_pipeline_stops_on_first_exception(monkeypatch, capsys):
    called = []
    for _, name, module in main.STAGES:
        def run(name=name):
            called.append(name)
            if name == "Database":
                raise RuntimeError("database failed")
        monkeypatch.setattr(module, "run", run)
    with pytest.raises(RuntimeError, match="database failed"):
        main.run_pipeline()
    assert called == ["Data Cleaning", "Synthetic Sales", "Database"]
    output = capsys.readouterr().out
    assert output.count("PASS") == 2
    assert "Project pipeline completed successfully." not in output
