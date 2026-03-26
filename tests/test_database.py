"""Tests for the Condition SQL query builder in database.py."""
import sqlite3
import pytest
from database import Condition


def test_empty_condition():
    c = Condition()
    assert c.sql() == "1"
    assert c.filler == []


def test_single_and_equal():
    c = Condition().and_equal("col", "val")
    assert c.sql() == "col=?"
    assert c.filler == ["val"]


def test_chained_or_equal():
    c = Condition().or_equal("col", "a").or_equal("col", "b")
    assert c.sql() == "col=? OR col=?"
    assert c.filler == ["a", "b"]


def test_and_equal_case_insensitive():
    c = Condition().and_equal("Name", "Alice", case_sensitive=False)
    assert c.sql() == "LOWER(Name)=?"
    assert c.filler == ["alice"]


def test_or_equal_case_insensitive():
    c = Condition().or_equal("Title", "ROCK", case_sensitive=False)
    assert c.sql() == "LOWER(Title)=?"
    assert c.filler == ["rock"]


def test_and_like():
    c = Condition().and_like("tags", "%jazz%")
    assert c.sql() == "tags LIKE ?"
    assert c.filler == ["%jazz%"]


def test_or_like():
    c = Condition().or_like("tags", "%pop%")
    assert c.sql() == "tags LIKE ?"
    assert c.filler == ["%pop%"]


def test_chained_and_like_or_like():
    c = Condition().and_like("tags", "%a%").or_like("tags", "%b%")
    sql = c.sql()
    assert "tags LIKE ?" in sql
    assert "OR tags LIKE ?" in sql
    assert c.filler == ["%a%", "%b%"]


def test_and_regexp():
    c = Condition().and_regexp("path", r"\.mp3$")
    assert "path REGEXP ?" in c.sql()
    assert c.filler == [r"\.mp3$"]
    assert c.has_regex is True


def test_or_regexp():
    c = Condition().or_regexp("path", r"\.flac$")
    assert "path REGEXP ?" in c.sql()
    assert c.has_regex is True


def test_limit():
    c = Condition().and_equal("type", "file").limit(10)
    assert "LIMIT 10" in c.sql()


def test_offset():
    c = Condition().and_equal("type", "file").limit(10).offset(5)
    sql = c.sql()
    assert "LIMIT 10" in sql
    assert "OFFSET 5" in sql


def test_order_by_asc():
    c = Condition().order_by("title")
    sql = c.sql()
    assert "ORDER BY title" in sql
    assert "DESC" not in sql


def test_order_by_desc():
    c = Condition().order_by("title", desc=True)
    sql = c.sql()
    assert "ORDER BY title" in sql
    assert "DESC" in sql


def test_chained_conditions_combined():
    c = (
        Condition()
        .and_equal("type", "file")
        .and_like("tags", "%rock%")
        .limit(20)
    )
    sql = c.sql()
    assert "type=?" in sql
    assert "AND tags LIKE ?" in sql
    assert "LIMIT 20" in sql
    assert c.filler == ["file", "%rock%"]


def test_filler_accumulates_across_chain():
    c = (
        Condition()
        .and_equal("a", "1")
        .or_equal("b", "2")
        .and_like("c", "%3%")
    )
    assert c.filler == ["1", "2", "%3%"]


def test_and_sub_condition():
    sub = Condition().and_equal("type", "url")
    c = Condition().and_equal("ready", "yes").and_sub_condition(sub)
    sql = c.sql()
    assert "ready=?" in sql
    assert "AND (type=?)" in sql
    assert c.filler == ["yes", "url"]


def test_and_not_sub_condition():
    sub = Condition().and_like("tags", "%don't autoplay,%")
    c = Condition().and_not_sub_condition(sub)
    sql = c.sql()
    assert "NOT" in sql
    assert sub.filler[0] in c.filler


def test_regexp_registers_function_and_matches():
    """sql(conn) registers REGEXP so the condition works in real queries."""
    c = Condition().and_regexp("path", r"\.mp3$")
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (path TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", ("/music/song.mp3",))
    conn.execute("INSERT INTO t VALUES (?)", ("/music/song.flac",))
    conn.commit()
    sql = c.sql(conn)
    rows = conn.execute(f"SELECT path FROM t WHERE {sql}", c.filler).fetchall()
    assert rows == [("/music/song.mp3",)]
    conn.close()
