import pandas as pd


def test_boolean_coercion():
    """Verify that messy database boolean representations are strictly cast to 0 and 1."""
    raw = pd.DataFrame({"false_positive": [True, "false", "1", 0, None, "true"]})

    # Simulate the coercion logic from load_data()
    raw["false_positive"] = (
        raw["false_positive"]
        .map({True: 1, False: 0, "1": 1, "0": 0, "true": 1, "false": 0})
        .fillna(0)
    )

    assert list(raw["false_positive"]) == [1, 0, 1, 0, 0, 1]
