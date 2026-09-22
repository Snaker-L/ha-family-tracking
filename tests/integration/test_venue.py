"""Working out what to call the place a fix is in, rather than what is nearest."""

from family_tracking.address import merge_venue, parse, street_line
from family_tracking.venue import (
    CONTAINERS,
    NEARBY,
    VENUE_KEYS,
    build_query,
    covers,
    pick_name,
)


def area(name, **tags):
    """An outline the fix is inside; this is what `is_in` returns."""
    return {"type": "area", "id": 1, "tags": {"name": name, **tags}}


def near(name, **tags):
    """Something merely close by; this is what the radius search returns."""
    return {"type": "way", "id": 2, "tags": {"name": name, **tags}}


class TestBuildQuery:
    def test_asks_what_contains_the_point(self):
        q = build_query(48.2536965, 16.3675578)
        assert q.startswith("[out:json][timeout:25];")
        assert "is_in(48.253696,16.367558)->.a;" in q

    def test_one_indexed_statement_per_key(self):
        # Not a regular expression over keys: that is not indexed and times the
        # service out. Verified against the live service, which answers this
        # form in about three seconds and the other one not at all.
        q = build_query(1.0, 2.0)
        for key in VENUE_KEYS:
            assert f'area.a[name]["{key}"];out tags;' in q

    def test_also_looks_around_the_point(self):
        # A stay is the centre of many samples and indoors those scatter, so
        # containment alone misses the building the person is standing in.
        q = build_query(48.2413091, 16.3855681, radius=50)
        assert 'nwr(around:50,48.241309,16.385568)[name]["shop"~"^(mall|department_store)$"];out tags;' in q
        assert 'nwr(around:50,48.241309,16.385568)[name]["landuse"~"^(retail)$"];out tags;' in q

    def test_the_radius_search_stays_narrow(self):
        # A café fifty metres away is somewhere else; a shopping centre fifty
        # metres away is where you are.
        assert all(key == "shop" or value == "retail" for key, value in NEARBY)

    def test_administrative_areas_are_not_asked_for(self):
        # Every fix is inside a district, a city and a country, and none of
        # those answers "where is she".
        assert "boundary" not in VENUE_KEYS
        assert "place" not in VENUE_KEYS

    def test_coordinates_are_not_written_in_exponential_form(self):
        assert "1e-" not in build_query(0.0000001, 0.0000001)


class TestPickName:
    def test_takes_the_enclosing_place(self):
        assert pick_name({"elements": [area("Stadion Center", shop="mall")]}) == "Stadion Center"

    def test_nothing_at_all(self):
        assert pick_name({"elements": []}) == ""
        assert pick_name({}) == ""

    def test_an_outline_without_a_name_is_no_answer(self):
        assert pick_name({"elements": [area("", shop="mall")]}) == ""

    def test_the_centre_beats_the_unit_inside_it(self):
        # Both contain the fix. Asked where she is, nobody says "Nespresso".
        payload = {"elements": [area("Nespresso", shop="coffee"), area("Q19", shop="mall")]}
        assert pick_name(payload) == "Q19"

    def test_something_containing_the_fix_beats_something_near_it(self):
        payload = {"elements": [near("Westfield Donau Zentrum", shop="mall"),
                                area("Bücherei", amenity="library")]}
        assert pick_name(payload) == "Bücherei"

    def test_the_radius_search_rescues_a_scattered_fix(self):
        # Millennium City with the fix forty metres outside the outline: this
        # is the case the radius search exists for.
        assert pick_name({"elements": [near("Millennium City", shop="mall")]}) == "Millennium City"

    def test_a_named_place_of_any_kind_still_counts(self):
        # The point is a special name rather than a street, whatever it is.
        assert pick_name({"elements": [area("AKH Wien", amenity="hospital")]}) == "AKH Wien"
        assert pick_name({"elements": [area("Stadthalle", leisure="sports_centre")]}) == "Stadthalle"

    def test_the_order_in_containers_decides(self):
        payload = {"elements": [area("Areal", landuse="retail"), area("Zentrum", shop="mall")]}
        assert pick_name(payload) == "Zentrum"
        assert CONTAINERS[0] == ("shop", "mall")


class TestMergeVenue:
    def test_the_place_replaces_the_street(self):
        a = parse({"address": {"road": "Wagramer Straße", "house_number": "94", "city": "Wien"}})
        assert a.label == "Wagramer Straße 94, Wien"
        assert merge_venue(a, "Westfield Donau Zentrum").label == "Westfield Donau Zentrum, Wien"

    def test_it_replaces_a_shop_inside_the_centre(self):
        a = parse({"name": "Nespresso", "address": {"shop": "Nespresso", "city": "Wien"}})
        merged = merge_venue(a, "Q19 Einkaufsquartier Döbling")
        assert merged.label == "Q19 Einkaufsquartier Döbling, Wien"
        assert merged.name == "Q19 Einkaufsquartier Döbling"

    def test_the_address_parts_survive_for_the_sensor(self):
        a = parse({"address": {"road": "Wagramer Straße", "house_number": "94",
                               "postcode": "1220", "city": "Wien"}})
        merged = merge_venue(a, "Westfield Donau Zentrum")
        assert (merged.street, merged.house_number, merged.postcode) == (
            "Wagramer Straße", "94", "1220")

    def test_nothing_encloses_the_fix_and_the_address_stands(self):
        a = parse({"address": {"road": "Hauptstraße", "house_number": "12", "city": "Wien"}})
        assert merge_venue(a, "").label == "Hauptstraße 12, Wien"

    def test_a_place_without_an_address_is_still_an_answer(self):
        merged = merge_venue(None, "Millennium City")
        assert merged.label == "Millennium City"

    def test_neither_service_answered(self):
        assert merge_venue(None, "") is None

    def test_a_place_without_a_known_city_needs_no_comma(self):
        assert merge_venue(parse({"address": {"road": "Landstraße"}}), "Stadion Center").label == "Stadion Center"

class TestMitAdresse:
    """Die Adresse zusätzlich, in Klammern hinter dem Namen."""

    def test_the_address_follows_the_name_in_brackets(self):
        a = parse({"address": {"road": "Olympiaplatz", "house_number": "2", "city": "Wien"}})
        assert merge_venue(a, "Stadion Center", with_address=True).label == (
            "Stadion Center (Olympiaplatz 2, Wien)")

    def test_the_city_is_not_named_twice(self):
        a = parse({"address": {"road": "Olympiaplatz", "house_number": "2", "city": "Wien"}})
        assert merge_venue(a, "Stadion Center", with_address=True).label.count("Wien") == 1

    def test_the_brackets_never_hold_the_shop_next_door(self):
        # Measured inside the Stadion Center: Nominatim answers with a shop and
        # no street at all. Putting that in brackets would name the very thing
        # the place was meant to replace.
        a = parse({"name": "TEDi", "address": {"shop": "TEDi", "city": "Wien"}})
        assert a.label == "TEDi, Wien"
        assert merge_venue(a, "Stadion Center", with_address=True).label == "Stadion Center, Wien"

    def test_without_a_house_number_the_street_still_counts(self):
        a = parse({"address": {"road": "Grinzinger Straße", "city": "Wien"}})
        assert merge_venue(a, "Q19", with_address=True).label == "Q19 (Grinzinger Straße, Wien)"

    def test_without_the_option_the_address_is_dropped(self):
        a = parse({"address": {"road": "Olympiaplatz", "house_number": "2", "city": "Wien"}})
        assert merge_venue(a, "Stadion Center").label == "Stadion Center, Wien"

    def test_nothing_encloses_the_fix_and_the_address_stands_alone(self):
        a = parse({"address": {"road": "Hauptstraße", "house_number": "12", "city": "Wien"}})
        assert merge_venue(a, "", with_address=True).label == "Hauptstraße 12, Wien"

    def test_a_place_without_an_address_needs_no_brackets(self):
        assert merge_venue(None, "Millennium City", with_address=True).label == "Millennium City"

    def test_the_parts_still_reach_the_sensor(self):
        a = parse({"address": {"road": "Olympiaplatz", "house_number": "2",
                               "postcode": "1020", "city": "Wien"}})
        m = merge_venue(a, "Stadion Center", with_address=True)
        assert (m.street, m.house_number, m.postcode, m.name) == (
            "Olympiaplatz", "2", "1020", "Stadion Center")


class TestAbdeckung:
    """Hat die antwortende Instanz überhaupt Daten für diese Weltgegend?"""

    def test_the_query_asks_how_many_areas_enclose_the_point(self):
        assert "area.a;out count;" in build_query(48.2537, 16.3676)

    def test_a_server_that_knows_the_region_reports_areas(self):
        # Gemessen: overpass-api.de meldet 11 Flächen für Wien, 7 für Zürich.
        assert covers({"elements": [{"type": "count", "tags": {"areas": "11"}}]}) is True

    def test_a_regional_mirror_reports_none(self):
        # Gemessen: overpass.osm.ch meldet 0 für Wien und Tokio, 6 für Zürich.
        # Ohne diese Unterscheidung hieße das "hier ist kein Ort" -- und würde
        # als Tatsache gespeichert.
        assert covers({"elements": [{"type": "count", "tags": {"areas": "0"}}]}) is False

    def test_an_answer_without_a_count_is_taken_at_face_value(self):
        assert covers({"elements": []}) is True
        assert covers({}) is True

    def test_an_unreadable_count_is_no_reason_to_throw_the_answer_away(self):
        assert covers({"elements": [{"type": "count", "tags": {"areas": "viele"}}]}) is True

    def test_the_count_element_is_not_mistaken_for_a_place(self):
        payload = {"elements": [{"type": "count", "tags": {"areas": "11"}},
                                {"type": "area", "id": 1, "tags": {"name": "Q19", "shop": "mall"}}]}
        assert pick_name(payload) == "Q19"


class TestSchreibweiseNachLand:
    """Nominatim liefert Straße und Hausnummer getrennt -- die Reihenfolge nicht."""

    def test_the_house_number_goes_first_where_that_country_does(self):
        for land, road, hnr, stadt, erwartet in [
            ("us", "5th Avenue", "350", "New York", "350 5th Avenue, New York"),
            ("ca", "Bremner Boulevard", "290", "Toronto", "290 Bremner Boulevard, Toronto"),
            ("gb", "Downing Street", "10", "London", "10 Downing Street, London"),
            ("fr", "Rue de Rivoli", "12", "Paris", "12 Rue de Rivoli, Paris"),
        ]:
            a = parse({"address": {"road": road, "house_number": hnr,
                                   "city": stadt, "country_code": land}})
            assert a.label == erwartet

    def test_and_after_the_street_everywhere_else(self):
        for land in ("de", "at", "nl", "it", "pl", ""):
            a = parse({"address": {"road": "Hauptstraße", "house_number": "12",
                                   "city": "Ort", "country_code": land}})
            assert a.label == "Hauptstraße 12, Ort"

    def test_the_brackets_follow_the_same_order(self):
        a = parse({"address": {"road": "5th Avenue", "house_number": "350",
                               "city": "New York", "country_code": "us"}})
        assert street_line(a) == "350 5th Avenue, New York"
        assert merge_venue(a, "Empire State Building", with_address=True).label == (
            "Empire State Building (350 5th Avenue, New York)")

    def test_the_country_code_survives_the_cache(self):
        a = parse({"address": {"road": "5th Avenue", "house_number": "350",
                               "city": "New York", "country_code": "us"}})
        from family_tracking.address import Address
        assert Address(**a.as_dict()).country_code == "us"
