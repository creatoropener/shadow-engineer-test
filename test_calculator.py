import pytest
from calculator import add, subtract, multiply, divide

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 2) == 3

def test_multiply():
    assert multiply(3, 4) == 12

def test_divide_normal():
    assert divide(6, 2) == 3.0

def test_divide_by_zero():
    # This test expects a ValueError, but our buggy script returns 0,
    # causing pytest to fail!
    with pytest.raises(ValueError):
        divide(10, 0)
