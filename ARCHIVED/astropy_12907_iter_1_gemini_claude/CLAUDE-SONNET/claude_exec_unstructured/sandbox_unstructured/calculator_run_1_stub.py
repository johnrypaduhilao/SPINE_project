class CalculatorError(Exception):
    pass

def divide(a, b):
    if b == 0:
        raise CalculatorError('division by zero')
    return a / b
