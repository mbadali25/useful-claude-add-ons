"""`crew_fixtures.link_path_dirs` builds one bin directory out of several PATH
dirs without raising on a name two of them share (L-0529).

The first self-hosted CI run (36735895881, Ubuntu 26.04) failed 42 tests per
leg with `FileExistsError: '/bin/grub-ntldr-img' -> '.../tools/grub-ntldr-img'`.
`/bin` is a symlink to `usr/bin` there, so the `/bin` pass revisits every
`/usr/bin` name, and the old skip test was `Path.exists()`, which follows
symlinks: `/usr/bin/grub-ntldr-img` is a relative link whose target is not
installed, so the farm's link to it dangled, read as absent, and the second
`os.symlink` raised. These cases rebuild that shape in `tmp_path`.
"""
import os

import pytest

import crew_fixtures

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX symlink farm; Windows uses Git's tool dir")


def test_a_dir_symlinked_to_another_holding_a_dangling_relative_link_does_not_raise(tmp_path):
    real = tmp_path / "usr" / "bin"
    real.mkdir(parents=True)
    (real / "grub-ntldr-img").symlink_to(os.path.join("..", "lib", "grub", "missing"))
    alias = tmp_path / "bin"
    alias.symlink_to(os.path.join("usr", "bin"), target_is_directory=True)
    farm = tmp_path / "farm"
    farm.mkdir()

    crew_fixtures.link_path_dirs(farm, (str(real), str(alias)))

    assert os.listdir(farm) == ["grub-ntldr-img"]


def test_two_distinct_dirs_holding_one_name_link_the_first_like_path_lookup(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    for directory in (first, second):
        directory.mkdir()
        (directory / "tool").write_text("#!/bin/sh\n", encoding="ascii", newline="\n")
    farm = tmp_path / "farm"
    farm.mkdir()

    crew_fixtures.link_path_dirs(farm, (str(first), str(second)))

    assert os.readlink(farm / "tool") == str(first / "tool")


def test_a_dangling_entry_in_the_first_dir_still_shadows_the_same_name_later(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / "tool").symlink_to("not-installed")
    (second / "tool").write_text("", encoding="ascii")
    farm = tmp_path / "farm"
    farm.mkdir()

    crew_fixtures.link_path_dirs(farm, (str(first), str(second)))

    assert os.readlink(farm / "tool") == str(first / "tool")


def test_a_dir_already_linked_through_an_alias_is_not_listed_again(tmp_path, monkeypatch):
    real = tmp_path / "usr" / "bin"
    real.mkdir(parents=True)
    (real / "tr").write_text("", encoding="ascii")
    alias = tmp_path / "bin"
    alias.symlink_to(os.path.join("usr", "bin"), target_is_directory=True)
    farm = tmp_path / "farm"
    farm.mkdir()
    listed = []
    real_listdir = os.listdir
    monkeypatch.setattr(crew_fixtures.os, "listdir", lambda d: listed.append(d) or real_listdir(d))

    crew_fixtures.link_path_dirs(farm, (str(real), str(alias)))

    assert listed == [str(real)]


def test_a_skipped_name_is_left_out_of_the_farm(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    for name in ("python3", "tr"):
        (source / name).write_text("", encoding="ascii")
    farm = tmp_path / "farm"
    farm.mkdir()

    crew_fixtures.link_path_dirs(farm, (str(source),), skip=lambda name: name.startswith("py"))

    assert os.listdir(farm) == ["tr"]


def test_a_missing_source_dir_is_passed_over(tmp_path):
    farm = tmp_path / "farm"
    farm.mkdir()

    crew_fixtures.link_path_dirs(farm, (str(tmp_path / "absent"),))

    assert os.listdir(farm) == []
