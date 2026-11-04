def test_required_ci_detects_a_deliberate_failure():
    raise AssertionError("Intentional failure: validating the required-ci gate")
