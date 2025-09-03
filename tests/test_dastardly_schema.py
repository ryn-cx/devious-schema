from typing import Any

from devious_schema import (
    get_schema,
    get_schema_from_strings,
    to_pascal_case,
    to_snake_case,
)


def test_to_snake_case() -> None:
    assert to_snake_case("camelCase") == "camel_case"
    assert to_snake_case("PascalCase") == "pascal_case"
    assert to_snake_case("snake_case") == "snake_case"
    assert to_snake_case("Nonsense_Case") == "nonsense_case"
    assert to_snake_case("__private_string") == "__private_string"
    assert to_snake_case("__privateString") == "__private_string"


def test_to_pascal_case() -> None:
    assert to_pascal_case("camelCase") == "CamelCase"
    assert to_pascal_case("PascalCase") == "PascalCase"
    assert to_pascal_case("snake_case") == "SnakeCase"
    assert to_pascal_case("__private_string") == "PrivateString"
    assert to_pascal_case("__privateString") == "PrivateString"


def test_root_list() -> None:
    data: list[Any] = [123, "abc"]
    expected = """from pydantic import BaseModel, Field, ConfigDict
from typing import Any


root: list[str | int]"""
    assert get_schema(data, "Root") == expected


def test_list_parameter() -> None:
    data: dict[str, list[Any]] = {"list": [123, "abc"]}
    expected = """from pydantic import BaseModel, Field, ConfigDict
from typing import Any


class Root(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list: list[str | int]"""
    assert (get_schema(data, "Root")) == expected


def test_params() -> None:
    data: dict[str, Any] = {
        "str": "String",
        "int": 123,
        "float": 123.45,
        "none": None,
        "list": [],
        "list_with_items": [123, "abc"],
        "dict_with_key": {"key": "value"},
        "empty_dict": {},
        "camelCaseString": "Came Case String",
        "camelCaseDict": {"key": "value"},
        "nested_list": [[1, 2, 3]],
        "__private_str_1": "Private String",
        "__privateStr2": "Private String",
    }
    expected = """from pydantic import BaseModel, Field, ConfigDict
from typing import Any


class RootCamelCaseDictDict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str


class RootDictWithKeyDict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str


class Root(BaseModel):
    model_config = ConfigDict(extra="forbid")
    str: str
    int: int
    float: float
    none: None
    list: list[Any]
    list_with_items: list[str | int]
    dict_with_key: "RootDictWithKeyDict"
    empty_dict: dict[str, Any]
    camel_case_string: str = Field(alias="camelCaseString")
    camel_case_dict: "RootCamelCaseDictDict" = Field(alias="camelCaseDict")
    nested_list: list[list[int]]
    private_str_1: str = Field(alias="__private_str_1")
    private_str2: str = Field(alias="__privateStr2")"""
    assert expected == get_schema(data, "Root")


def test_combined_dict_schema() -> None:
    params: list[dict[str, Any]] = [{"a": "b"}, {"a": 123}]
    expected = """from pydantic import BaseModel, Field, ConfigDict
from typing import Any


class Root(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: str | int"""
    assert expected == get_schema_from_strings(params, "Root")


def test_combined_list_schema() -> None:
    params: list[Any] = [["asd"], [123]]
    expected = """from pydantic import BaseModel, Field, ConfigDict
from typing import Any


root: list[str | int]"""
    assert expected == get_schema_from_strings(params, "Root")


def test_combined_schema() -> None:
    params: list[Any] = [["asd"], [123], {"a": 123}]
    expected = """from pydantic import BaseModel, Field, ConfigDict
from typing import Any


class RootDict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: int


root: "RootDict" | list[str | int]"""
    assert expected == get_schema_from_strings(params, "Root")
