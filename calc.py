import ast
import operator as op
import functools


def is_integer(st):
    try:
        int(st)
    except ValueError:
        return False
    return True


# supported operators
operators = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
             ast.Div: op.truediv, ast.Pow: op.pow, ast.BitXor: op.xor,
             ast.USub: op.neg, ast.BitAnd: op.and_, ast.BitOr: op.or_,
             ast.Invert: op.invert, ast.FloorDiv: op.floordiv}


def eval_expr(expr):
    """
    >>> eval_expr('2^6')
    4
    >>> eval_expr('2**6')
    64
    >>> eval_expr('1 + 2*3**(4^5) / (6 + -7)')
    -5.0
    """
    return evil_(ast.parse(expr, mode='eval').body)


MAXVAL = 1e50
MAXPOW = 100


def eval_(node):
    if isinstance(node, ast.Num):  # <number>
        if node.n > MAXVAL:
            raise ValueError(f"Value {node.n} is too large")
        return node.n
    elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
        left = eval_(node.left)
        right = eval_(node.right)

        if isinstance(node.op, ast.Pow):
            if right > MAXPOW:
                raise ValueError(f"Power {right} is too large")

        val = operators[type(node.op)](eval_(node.left), eval_(node.right))
        if abs(val) > MAXVAL:
            raise ValueError(f"Value {val} is too large")
        return val
    elif isinstance(node, ast.UnaryOp):  # <operator> <operand> e.g., -1
        val = operators[type(node.op)](eval_(node.operand))
        if abs(val) > MAXVAL:
            raise ValueError(f"Value {val} is too large")
        return val
    else:
        raise TypeError(f'{node} t = {type(node)}')


def limit(max_=None):
    """Return decorator that limits allowed returned values."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ret = func(*args, **kwargs)
            try:
                mag = abs(ret)
            except TypeError:
                pass  # not applicable
            else:
                if mag > max_:
                    raise ValueError(ret)
            return ret

        return wrapper

    return decorator


evil_ = limit(max_=10 ** 100)(eval_)
