from gitlabform.processors.defining_keys import And, Key, OptionalKey, Or, Xor


class TestKey:
    def test_matches_when_both_have_same_value(self):
        assert Key("name").matches({"name": "foo"}, {"name": "foo"})

    def test_does_not_match_when_values_differ(self):
        assert not Key("name").matches({"name": "foo"}, {"name": "bar"})

    def test_does_not_match_when_key_missing_in_either(self):
        assert not Key("name").matches({"name": "foo"}, {})
        assert not Key("name").matches({}, {"name": "foo"})

    def test_contains_returns_true_when_present_and_not_none(self):
        assert Key("name").contains({"name": "foo"})

    def test_contains_returns_false_when_missing(self):
        assert not Key("name").contains({})

    def test_contains_returns_false_when_value_is_none(self):
        assert not Key("name").contains({"name": None})

    def test_explain_quotes_the_key_name(self):
        assert Key("name").explain() == "'name'"


class TestAnd:
    def test_matches_when_all_keys_match(self):
        and_key = And(Key("a"), Key("b"))
        assert and_key.matches({"a": 1, "b": 2}, {"a": 1, "b": 2})

    def test_does_not_match_when_any_key_fails(self):
        and_key = And(Key("a"), Key("b"))
        assert not and_key.matches({"a": 1, "b": 2}, {"a": 1, "b": 99})

    def test_contains_requires_all_keys(self):
        and_key = And(Key("a"), Key("b"))
        assert and_key.contains({"a": 1, "b": 2})
        assert not and_key.contains({"a": 1})

    def test_explain_joins_with_and(self):
        assert And(Key("a"), Key("b")).explain() == "('a' and 'b')"


class TestOr:
    def test_matches_when_any_key_matches(self):
        or_key = Or(Key("a"), Key("b"))
        assert or_key.matches({"a": 1}, {"a": 1})
        assert or_key.matches({"b": 2}, {"b": 2})

    def test_does_not_match_when_no_key_matches(self):
        or_key = Or(Key("a"), Key("b"))
        assert not or_key.matches({"a": 1}, {"a": 2})

    def test_contains_requires_any_key(self):
        or_key = Or(Key("a"), Key("b"))
        assert or_key.contains({"a": 1})
        assert or_key.contains({"b": 2})
        assert not or_key.contains({"c": 3})

    def test_explain_joins_with_or(self):
        assert Or(Key("a"), Key("b")).explain() == "('a' or 'b')"


class TestXor:
    def test_matches_when_exactly_one_matches(self):
        xor = Xor(Key("a"), Key("b"))
        assert xor.matches({"a": 1, "b": 99}, {"a": 1, "b": 100})

    def test_does_not_match_when_both_match(self):
        xor = Xor(Key("a"), Key("b"))
        assert not xor.matches({"a": 1, "b": 2}, {"a": 1, "b": 2})

    def test_does_not_match_when_none_match(self):
        xor = Xor(Key("a"), Key("b"))
        assert not xor.matches({"a": 1, "b": 2}, {"a": 9, "b": 9})

    def test_contains_requires_exactly_one_key(self):
        xor = Xor(Key("a"), Key("b"))
        assert xor.contains({"a": 1})
        assert xor.contains({"b": 2})
        assert not xor.contains({"a": 1, "b": 2})
        assert not xor.contains({})

    def test_explain_lists_alternatives(self):
        assert Xor(Key("a"), Key("b")).explain() == "(exactly one of: 'a', 'b')"


class TestOptionalKey:
    def test_does_not_match_when_absent_in_both(self):
        # Quirk of the implementation: matches() returns False when the key is
        # missing on both sides. In practice OptionalKey is combined with another
        # mandatory key via And(), so this branch is never the deciding factor.
        assert not OptionalKey("name").matches({}, {})

    def test_matches_when_only_in_one(self):
        opt = OptionalKey("name")
        assert opt.matches({"name": "x"}, {})
        assert opt.matches({}, {"name": "x"})

    def test_matches_when_in_both_with_equal_value(self):
        assert OptionalKey("name").matches({"name": "x"}, {"name": "x"})

    def test_does_not_match_when_in_both_with_different_values(self):
        assert not OptionalKey("name").matches({"name": "x"}, {"name": "y"})

    def test_contains_always_returns_true(self):
        opt = OptionalKey("name")
        assert opt.contains({})
        assert opt.contains({"name": "x"})

    def test_explain_marks_optional(self):
        assert OptionalKey("name").explain() == "(optionally 'name')"
