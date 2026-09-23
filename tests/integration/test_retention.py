"""Where each retention choice ends."""

from datetime import datetime, timezone

from family_tracking.retention import (
    cutoff_for,
    format_keep,
    parse_keep,
    subtract_months,
    validate_keep,
)

UTC = timezone.utc


class TestValidateKeep:
    def test_takes_a_value_from_the_list(self):
        assert validate_keep("10d") == ("10d", None, "")
        assert validate_keep("3m") == ("3m", None, "")

    def test_understands_short_and_written_units(self):
        for text, keep in (
            ("40 T", "40d"),
            ("40t", "40d"),
            ("18 M", "18m"),
            ("3 J", "3y"),
            ("2 J.", "2y"),
            ("40 Tage", "40d"),
            ("18 Monate", "18m"),
            ("1 Jahr", "1y"),
            ("6 months", "6m"),
            ("2 y", "2y"),
        ):
            assert validate_keep(text) == (keep, None, ""), text

    def test_a_bare_number_means_days(self):
        assert validate_keep("40") == ("40d", None, "")

    def test_says_the_number_is_missing(self):
        for text in ("", "   ", "Tage", "0 T", "-3 T", None):
            assert validate_keep(text) == (None, "keep_no_number", ""), text

    def test_quotes_a_number_with_decimals(self):
        assert validate_keep("1,5 J") == (None, "keep_whole_number", "1,5")
        assert validate_keep("1.5 Jahre") == (None, "keep_whole_number", "1.5")

    def test_quotes_an_unknown_unit(self):
        assert validate_keep("3 Wochen") == (None, "keep_unknown_unit", "Wochen")
        assert validate_keep("3 x") == (None, "keep_unknown_unit", "x")

    def test_caps_at_twenty_years(self):
        assert validate_keep("20 J") == ("20y", None, "")
        assert validate_keep("21 J") == (None, "keep_too_long", "")
        assert validate_keep("241 M") == (None, "keep_too_long", "")
        assert validate_keep("7400 T") == (None, "keep_too_long", "")


class TestFormatKeep:
    def test_writes_a_typed_setting_out(self):
        assert format_keep("40d", "de") == "40 Tage"
        assert format_keep("1y", "de") == "1 Jahr"
        assert format_keep("18m", "en") == "18 months"

    def test_falls_back_to_english(self):
        assert format_keep("2y", "fr") == "2 years"


class TestParseKeep:
    def test_reads_what_was_stored(self):
        assert parse_keep("40d") == (40, "d")
        assert parse_keep("2y") == (2, "y")

    def test_refuses_anything_else(self):
        for keep in ("", "d", "0m", "3w", None, 10):
            assert parse_keep(keep) is None


class TestSubtractMonths:
    def test_keeps_the_day(self):
        assert subtract_months(datetime(2026, 9, 23, 4, tzinfo=UTC), 3) == datetime(
            2026, 6, 23, 4, tzinfo=UTC
        )

    def test_clamps_to_a_shorter_month(self):
        assert subtract_months(datetime(2026, 3, 31, tzinfo=UTC), 1) == datetime(
            2026, 2, 28, tzinfo=UTC
        )
        assert subtract_months(datetime(2028, 3, 31, tzinfo=UTC), 1) == datetime(
            2028, 2, 29, tzinfo=UTC
        )

    def test_crosses_the_year(self):
        assert subtract_months(datetime(2026, 1, 15, tzinfo=UTC), 2) == datetime(
            2025, 11, 15, tzinfo=UTC
        )


class TestCutoff:
    NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)

    def test_days(self):
        assert cutoff_for("10d", self.NOW) == datetime(2026, 9, 13, 12, tzinfo=UTC)

    def test_months_and_years(self):
        assert cutoff_for("1m", self.NOW) == datetime(2026, 8, 23, 12, tzinfo=UTC)
        assert cutoff_for("11m", self.NOW) == datetime(2025, 10, 23, 12, tzinfo=UTC)
        assert cutoff_for("5y", self.NOW) == datetime(2021, 9, 23, 12, tzinfo=UTC)

    def test_any_number_of_days(self):
        assert cutoff_for("40d", self.NOW) == datetime(2026, 8, 14, 12, tzinfo=UTC)

    def test_unknown_choice_falls_back_to_ten_days(self):
        assert cutoff_for("forever", self.NOW) == cutoff_for("10d", self.NOW)
