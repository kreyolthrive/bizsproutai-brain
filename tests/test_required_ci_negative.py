def test_required_ci_detects_a_deliberate_failure():
    assert False, "Intentional failure: validating the required-ci gate"
