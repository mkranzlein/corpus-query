"""Tests for the roster loader."""

from __future__ import annotations

import pytest

from corpus_query.transcripts.roster import (
    Person,
    RosterError,
    describe_roster,
    first_names,
    read_roster,
)

TABLE = """# Roster

| First Name | Role   | Department  |
| ---------- | ------ | ----------- |
| Priya      | CEO    | Executive   |
| Marcus     | Head of Hardware Engineering | Engineering |
"""


def write_roster(tmp_path, text: str):
    """Write roster markdown to a temporary file and return its path."""
    path = tmp_path / "roster.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_rows_are_read_in_table_order(tmp_path):
    people = read_roster(write_roster(tmp_path, TABLE))
    assert people == (
        Person("Priya", "CEO", "Executive"),
        Person("Marcus", "Head of Hardware Engineering", "Engineering"),
    )


def test_the_header_and_its_rule_are_not_people(tmp_path):
    names = first_names(read_roster(write_roster(tmp_path, TABLE)))
    assert names == ("Priya", "Marcus")


def test_the_committed_roster_is_the_ten_person_cast(roster_path):
    people = read_roster(roster_path)
    names = first_names(people)
    assert len(people) == 10
    assert len(set(names)) == 10
    assert "Priya" in names


def test_the_roster_renders_one_line_per_person(tmp_path):
    described = describe_roster(read_roster(write_roster(tmp_path, TABLE)))
    assert described.splitlines() == [
        "- Priya (CEO, Executive)",
        "- Marcus (Head of Hardware Engineering, Engineering)",
    ]


def test_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(RosterError, match="Could not read"):
        read_roster(tmp_path / "nope.md")


def test_a_file_with_no_table_is_an_error(tmp_path):
    with pytest.raises(RosterError, match="no roster rows"):
        read_roster(write_roster(tmp_path, "# Roster\n\nNobody works here.\n"))


def test_a_row_of_the_wrong_width_is_an_error(tmp_path):
    text = TABLE + "| Sofia | Firmware Engineer |\n"
    with pytest.raises(RosterError, match="2 cells"):
        read_roster(write_roster(tmp_path, text))


def test_a_repeated_first_name_is_an_error(tmp_path):
    text = TABLE + "| Priya | Firmware Engineer | Engineering |\n"
    with pytest.raises(RosterError, match="more than once"):
        read_roster(write_roster(tmp_path, text))
