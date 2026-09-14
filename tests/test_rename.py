"""
Tests for Naming and Renaming.

The only destructive thing either tab does, so the tests are about what it
refuses as much as what it does. Every one of these works on files pytest
made in a temp folder — nothing here needs a model, and nothing touches a
real project.
"""

import json

import pytest

from src.core.models import NamingScheme, ShotRecord
from src.identifier.rename import (
    RENAME_LOG,
    apply_renames,
    check_plan,
    number_shots,
    planned_name,
    undo_renames,
)


def shots(directory, count=3, approved=True):
    """A folder of small files standing in for shots."""
    records = []

    for index in range(1, count + 1):
        path = directory / f"export_shot_{index:03d}.mp4"
        path.write_bytes(b"not really a video")
        records.append(ShotRecord(file=str(path), approved=approved))

    return records


# --- THE SCHEME ---


def test_the_scheme_counts_from_the_number_given():
    """The convention in the brief, exactly as it was written down."""
    scheme = NamingScheme(
        prefix="PARA_003_", start="4560", increment=20, suffix="_blockout_v0001"
    )

    assert scheme.name_for(0) == "PARA_003_4560_blockout_v0001"
    assert scheme.name_for(1) == "PARA_003_4580_blockout_v0001"


def test_the_number_is_padded_to_the_width_it_was_typed_at():
    """
    '0010' means four digits, '10' means two. The width is not a setting of
    its own because the person typing the first number has already said it.
    """
    assert NamingScheme(start="0010").name_for(0) == "0010"
    assert NamingScheme(start="10").name_for(0) == "10"
    assert NamingScheme(start="0010", increment=10).name_for(99) == "1000"


def test_nothing_is_added_between_the_parts():
    """Separators belong to the convention, so they are the user's to type."""
    scheme = NamingScheme(prefix="A", start="1", suffix="B")

    assert scheme.name_for(0) == "A1B"


def test_numbering_replaces_a_number_a_shot_already_had():
    """
    A second press after correcting the increment has to renumber the batch.
    Skipping the numbered ones would leave two conventions in one folder.
    """
    records = [ShotRecord(file="a.mp4", shot_number="OLD_001")]

    number_shots(records, NamingScheme(prefix="NEW_", start="010"))

    assert records[0].shot_number == "NEW_010"


# --- THE PLAN ---


def test_a_good_plan_has_no_problems(tmp_path):
    records = shots(tmp_path)
    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))

    assert check_plan(records) == []


def test_the_extension_is_kept(tmp_path):
    """The name changes; what kind of file it is does not."""
    records = shots(tmp_path, count=1)
    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))

    assert planned_name(records[0]) == "SEQ_0010.mp4"


def test_two_shots_given_the_same_name_is_refused(tmp_path):
    records = shots(tmp_path, count=2)
    for record in records:
        record.shot_number = "SEQ_0010"

    problems = check_plan(records)

    assert problems, "a collision was allowed through"
    assert "would both become" in problems[0]


def test_a_name_that_is_not_a_filename_is_refused(tmp_path):
    records = shots(tmp_path, count=1)
    records[0].shot_number = "SEQ/0010"

    assert any("cannot be a filename" in problem for problem in check_plan(records))


def test_a_target_that_already_exists_is_refused(tmp_path):
    records = shots(tmp_path, count=1)
    records[0].shot_number = "SEQ_0010"
    (tmp_path / "SEQ_0010.mp4").write_bytes(b"in the way")

    assert any("already exists" in problem for problem in check_plan(records))


def test_a_file_that_has_moved_is_refused(tmp_path):
    records = shots(tmp_path, count=1)
    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))
    (tmp_path / "export_shot_001.mp4").unlink()

    assert any("no longer where it was" in problem for problem in check_plan(records))


def test_an_unapproved_shot_is_not_in_the_plan(tmp_path):
    """Approval is the gate. A number alone renames nothing."""
    records = shots(tmp_path, count=2, approved=False)
    for record in records:
        record.shot_number = "SEQ_0010"

    assert check_plan(records) == [], "unapproved shots were planned"


# --- APPLYING IT ---


def test_the_files_are_renamed_and_the_records_updated(tmp_path):
    records = shots(tmp_path)
    number_shots(
        records,
        NamingScheme(prefix="PARA_003_", start="4560", increment=20, suffix="_blockout_v0001"),
    )

    apply_renames(records, tmp_path)

    on_disk = sorted(path.name for path in tmp_path.glob("*.mp4"))
    assert on_disk == [
        "PARA_003_4560_blockout_v0001.mp4",
        "PARA_003_4580_blockout_v0001.mp4",
        "PARA_003_4600_blockout_v0001.mp4",
    ]
    assert records[0].renamed_to == "PARA_003_4560_blockout_v0001.mp4"


def test_the_name_it_arrived_as_is_kept(tmp_path):
    """
    The tie back to the mini cut. After a rename nothing else on the record
    knows what the file was called, and the export has a column for it.
    """
    records = shots(tmp_path, count=1)
    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))

    apply_renames(records, tmp_path)

    assert records[0].original_file == "export_shot_001.mp4"


def test_a_bad_plan_renames_nothing(tmp_path):
    """
    Half a batch renamed is the worst outcome: some files moved, some not, and
    no way to tell which without reading the log.
    """
    records = shots(tmp_path, count=2)
    for record in records:
        record.shot_number = "SEQ_0010"

    with pytest.raises(ValueError):
        apply_renames(records, tmp_path)

    assert sorted(path.name for path in tmp_path.glob("*.mp4")) == [
        "export_shot_001.mp4",
        "export_shot_002.mp4",
    ]


def test_the_log_is_written_before_anything_moves(tmp_path):
    records = shots(tmp_path, count=1)
    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))

    apply_renames(records, tmp_path)
    entries = json.loads((tmp_path / RENAME_LOG).read_text(encoding="utf-8"))

    assert entries[0]["original"] == "export_shot_001.mp4"
    assert entries[0]["renamed_to"] == "SEQ_0010.mp4"


# --- UNDOING IT ---


def test_a_renamed_batch_goes_back(tmp_path):
    records = shots(tmp_path)
    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))
    apply_renames(records, tmp_path)

    restored = undo_renames(tmp_path)

    assert restored == 3
    assert sorted(path.name for path in tmp_path.glob("*.mp4")) == [
        "export_shot_001.mp4",
        "export_shot_002.mp4",
        "export_shot_003.mp4",
    ]
    assert not (tmp_path / RENAME_LOG).exists(), "a spent log was left behind"


def test_a_file_renamed_by_hand_since_is_left_alone(tmp_path):
    """
    The log says what this tool did. It is not a claim to own the folder
    afterwards, so a file someone has moved on from is reported, not forced.
    """
    records = shots(tmp_path, count=2)
    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))
    apply_renames(records, tmp_path)

    (tmp_path / "SEQ_0010.mp4").rename(tmp_path / "someone_elses_name.mp4")

    assert undo_renames(tmp_path) == 1
    assert (tmp_path / "someone_elses_name.mp4").is_file()


def test_undoing_nothing_is_not_an_error(tmp_path):
    assert undo_renames(tmp_path) == 0


def test_numbering_alone_approves_nothing(tmp_path):
    """
    The gate that made a rename silently do nothing. Numbering proposes names;
    approval is a separate act, and the UI attaches it when someone presses the
    destructive button. If this ever starts approving, the proposal step has
    stopped being a proposal.
    """
    records = shots(tmp_path, approved=False)

    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))

    assert all(record.shot_number for record in records)
    assert not any(record.approved for record in records)
    assert check_plan(records) == []

    apply_renames(records, tmp_path)

    assert sorted(path.name for path in tmp_path.glob("*.mp4")) == [
        "export_shot_001.mp4", "export_shot_002.mp4", "export_shot_003.mp4"
    ]
    assert not any(record.renamed_to for record in records), (
        "a record claimed it had moved when nothing did"
    )


def test_a_record_that_moved_says_so_and_one_that_did_not_stays_silent(tmp_path):
    """
    `renamed_to` is what the status line counts, so it has to mean the file
    actually moved — not that it was planned.
    """
    records = shots(tmp_path, count=2, approved=False)
    number_shots(records, NamingScheme(prefix="SEQ_", start="0010"))
    records[0].approved = True

    apply_renames(records, tmp_path)

    assert records[0].renamed_to == "SEQ_0010.mp4"
    assert records[1].renamed_to is None
