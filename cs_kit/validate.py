from typing import Callable
from functools import reduce
import copy
import itertools
import json
import uuid

import s3like


from .exceptions import CSKitError, SerializationError
from .schemas import Parameters, ErrorsWarnings


def load_model_parameters(model_parameters):
    for sect, _defaults in model_parameters.items():
        params = type(f"Params{sect}", (Parameters,), {"defaults": _defaults})()
        assert params


def check_get_inputs(inputs):
    if not isinstance(inputs, dict) or not set(inputs.keys()) == {
        "meta_parameters",
        "model_parameters",
    }:
        raise CSKitError(
            "Function 'get_inputs' must return a dictionary with keys: "
            "'meta_parameters' and 'model_parameters'"
        )


def check_validate_inputs(validate_res):
    if not isinstance(validate_res, dict):
        raise CSKitError("Function 'validate_res' must return a dictionary.")

    if "errors_warnings" not in validate_res:
        raise CSKitError("Function 'validate_res' must include 'errors_warnings'.")

    if validate_res.keys() - {"errors_warnings", "custom_adjustment"}:
        raise CSKitError(
            f"\nFunction 'validate_res' may only return a dictionary with "
            f"keys: \n'errors_warnings' and 'custom-adjustment'.\n"
            f"Keys {', '.join(validate_res.keys() - {'errors_warnings', 'custom_adjustment'})} "
            f"were also included."
        )


class CoreTestMeta(type):
    def __new__(cls, clsname, bases, attrs):
        print(attrs)
        for attr in ["get_version", "get_inputs", "validate_inputs", "run_model"]:
            if attrs.get(attr):
                attrs[attr] = staticmethod(attrs[attr])
        return super(CoreTestMeta, cls).__new__(cls, clsname, bases, attrs)


class CoreTestFunctions(metaclass=CoreTestMeta):
    get_version: Callable[[], str]
    get_inputs: Callable[[dict], tuple]
    validate_inputs: Callable[[dict, dict], tuple]
    run_model: Callable[[dict, dict], dict]
    ok_adjustment: dict
    bad_adjustment: dict

    def test_all_data_specified(self):
        for function in ["get_version", "get_inputs", "validate_inputs", "run_model"]:
            if not hasattr(self, function):
                raise CSKitError(
                    f"Function '{function}' was not set on the test class."
                )

        if not hasattr(self, "ok_adjustment"):
            raise CSKitError(
                "An example of valid data must be set on the test class as 'ok_adjustment'"
            )

        if not hasattr(self, "ok_adjustment"):
            raise CSKitError(
                "An example of invalid data must be set on the test class as 'bad_adjustment'"
            )

    def test_get_version(self):
        self.test_all_data_specified()
        assert self.get_version()

    def test_get_inputs(self):
        self.test_all_data_specified()
        inputs = self.get_inputs({})
        check_get_inputs(inputs)
        init_metaparams = inputs["meta_parameters"]
        init_modparams = inputs["model_parameters"]

        try:
            json.dumps(init_metaparams)
        except TypeError as e:
            raise SerializationError(
                (
                    f"Meta parameters must be JSON serializable: \n\n\t{str(e)}\n"
                    f"\nHint: try setting `serializable=True` in `Parameters.specification`."
                )
            )

        try:
            json.dumps(init_modparams)
        except TypeError as e:
            raise SerializationError(
                (
                    f"Model parameters must be JSON serializable: \n\n\t{str(e)}\n"
                    f"\nHint: try setting `serializable=True` in `Parameters.specification`."
                )
            )

        class MetaParams(Parameters):
            array_first = True
            defaults = init_metaparams

        metaparams = MetaParams()
        assert metaparams

        load_model_parameters(init_modparams)

        mp_grid = []
        mp_names = list(metaparams.keys())
        for mp_name in mp_names:
            mp_grid.append(metaparams.param_grid(mp_name))

        n_combinations = reduce(lambda x, y: len(x) * len(y), mp_grid, [1])
        mp_grid = itertools.product(*mp_grid)

        skip = n_combinations > 9
        for loopcount, tup in enumerate(mp_grid):
            if skip and not loopcount % 3:
                continue
            new_inputs = self.get_inputs(
                {mp_names[i]: tup[i] for i in range(len(metaparams.keys()))}
            )
            load_model_parameters(new_inputs["model_parameters"])

    def test_validate_inputs(self):
        self.test_all_data_specified()
        inputs = self.get_inputs({})
        check_get_inputs(inputs)

        init_metaparams = inputs["meta_parameters"]
        init_modparams = inputs["model_parameters"]

        class MetaParams(Parameters):
            array_first = True
            defaults = init_metaparams

        mp_spec = MetaParams().items()

        ew_template = {
            major_sect: {"errors": {}, "warnings": {}} for major_sect in init_modparams
        }
        ew_schema = ErrorsWarnings()

        valid_res = self.validate_inputs(
            mp_spec, self.ok_adjustment, copy.deepcopy(ew_template)
        )
        check_validate_inputs(valid_res)
        for major_sect, ew_dict in valid_res["errors_warnings"].items():
            ew_schema.load(ew_dict)
            if len(ew_dict.get("errors")) > 0:
                raise CSKitError(
                    f"Expected section {major_sect} to be valid but it has errors:\n"
                    f"{ew_dict}"
                )

        if valid_res.get("custom_adjustment"):
            try:
                json.dumps(valid_res["custom_adjustment"])
            except TypeError as e:
                raise SerializationError(
                    f"Parameters must be JSON serializable: \n\n\t{str(e)}\n"
                )

        invalid_res = self.validate_inputs(
            mp_spec, self.bad_adjustment, copy.deepcopy(ew_template)
        )
        check_validate_inputs(valid_res)
        for major_sect, ew_dict in invalid_res["errors_warnings"].items():
            ew_schema.load(ew_dict)
            if len(ew_dict.get("errors")) == 0:
                raise CSKitError(f"Expected section {major_sect} to have errors.")

        if invalid_res.get("custom_adjustment"):
            try:
                json.dumps(invalid_res["custom_adjustment"])
            except TypeError as e:
                raise SerializationError(
                    f"Parameters must be JSON serializable: \n\n\t{str(e)}\n"
                )

    def test_run_model(self):
        self.test_all_data_specified()
        inputs = self.get_inputs({})
        check_get_inputs(inputs)

        class MetaParams(Parameters):
            array_first = True
            defaults = inputs["meta_parameters"]

        mp_spec = MetaParams().items()

        result = self.run_model(mp_spec, self.ok_adjustment)

        assert s3like.LocalResult().load(result)
        assert s3like.write_to_s3like(uuid.uuid4(), result, do_upload=False)
