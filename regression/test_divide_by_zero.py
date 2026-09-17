import pytest
from calculator import divide

def test_divide_by_zero():
    with pytest.raises(ValueError):
        divide(10, 0)
