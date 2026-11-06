"""Which persons the integration follows."""

from family_tracking.people import persons_to_follow

ALEX = "person.hruza_alexander"
CLAUDIA = "person.claudia_hruza_claudia"


class TestPersonsToFollow:
    def test_follows_everyone_when_nobody_is_configured(self):
        assert persons_to_follow(None, [ALEX], [ALEX, CLAUDIA]) == [CLAUDIA, ALEX]

    def test_follows_only_the_configured_ones(self):
        assert persons_to_follow([ALEX], [ALEX, CLAUDIA], [ALEX, CLAUDIA]) == [ALEX]

    # A person from Remote Home Assistant has no state until that connection is
    # up. Treating them as gone cost them their sensors and, worse, their device
    # with its name and area.
    def test_keeps_a_configured_person_whose_state_is_not_there_yet(self):
        assert persons_to_follow([ALEX, CLAUDIA], [ALEX], [ALEX, CLAUDIA]) == [ALEX, CLAUDIA]

    def test_keeps_such_a_person_when_following_everyone(self):
        assert CLAUDIA in persons_to_follow(None, [ALEX], [ALEX, CLAUDIA])

    def test_a_person_with_a_state_but_no_registry_entry_still_counts(self):
        assert persons_to_follow([CLAUDIA], [CLAUDIA], []) == [CLAUDIA]

    # Deleted, or renamed to another entity id: the device for it may go.
    def test_drops_a_configured_person_home_assistant_does_not_know(self):
        assert persons_to_follow([ALEX, "person.gone"], [ALEX], [ALEX]) == [ALEX]

    def test_keeps_the_configured_order(self):
        assert persons_to_follow([CLAUDIA, ALEX], [], [ALEX, CLAUDIA]) == [CLAUDIA, ALEX]
