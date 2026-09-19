"""Working out what to call the place a fix is in, rather than what is nearest."""

from family_tracking.address import merge_venue, parse
from family_tracking.venue import CONTAINERS, NEARBY, VENUE_KEYS, build_query, pick_name


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
