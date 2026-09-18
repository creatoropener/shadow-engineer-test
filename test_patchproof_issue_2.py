import pytest
from calculator import divide


def test_divide_by_zero_raises():
    with pytest.raises(ValueError):
        divide(1, 0)


def test_divide_normal():
    assert divide(10, 2) == 5
