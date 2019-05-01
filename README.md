# Comp-Developer-Toolkit

`compdevkit` tests your model's functions against the COMP criteria. If your functions pass the `compdevkit` tests, then you can be reasonably sure that the functions will work on COMPmodels.org.

## Install `compdevkit`

```bash
pip install compdevkit
```

## Set up the `comp` directory
```bash
cdk-init
```

## Test your functions
```python
from compdevkit import FunctionsTest

import matchups

def test_get_parameters():
    ta = FunctionsTest(
        model_parameters=matchups.get_inputs,
        validate_inputs=matchups.validate_inputs,
        run_model=matchups.get_matchup,
        ok_adjustment={"matchup": {"pitcher": [{"value": "Max Scherzer"}]}},
        bad_adjustment={"matchup": {"pitcher": [{"value": "Not a pitcher"}]}}
    )
    ta.test()

```