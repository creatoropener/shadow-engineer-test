def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    # INTENTIONAL BUG: This should handle division by zero, 
    # but instead it crashes or returns the wrong value.
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
