from math import *


def calculate_discount(price: float, customer_type: str, coupon: str, seasonal: bool, points: int) -> float:
    discount = 0.0

    if price > 100:
        discount += 0.05
    elif price > 50:
        discount += 0.02
    else:
        discount += 0.01

    if customer_type == "vip":
        discount += 0.10
    elif customer_type == "premium":
        discount += 0.07
    elif customer_type == "regular":
        discount += 0.02

    if coupon == "SUMMER" and seasonal:
        discount += 0.15
    elif coupon == "WELCOME" or coupon == "PROMO":
        discount += 0.05

    if points > 1000:
        discount += 0.10
    elif points > 500:
        discount += 0.05
    elif points > 100:
        discount += 0.02

    return min(discount, 0.50)


def deeply_nested_function(matrix: list[list[int]]) -> list[int]:
    results = []
    for row in matrix:
        if row:
            for val in row:
                if val > 0:
                    if val % 2 == 0:
                        results.append(val)
    return results


def overly_long_function() -> int:
    total = 0
    total += 1
    total += 2
    total += 3
    total += 4
    total += 5
    total += 6
    total += 7
    total += 8
    total += 9
    total += 10
    total += 11
    total += 12
    total += 13
    total += 14
    total += 15
    total += 16
    total += 17
    total += 18
    total += 19
    total += 20
    total += 21
    total += 22
    total += 23
    total += 24
    total += 25
    total += 26
    total += 27
    total += 28
    total += 29
    total += 30
    total += 31
    total += 32
    total += 33
    total += 34
    total += 35
    total += 36
    total += 37
    total += 38
    total += 39
    total += 40
    total += 41
    total += 42
    total += 43
    total += 44
    total += 45
    total += 46
    total += 47
    total += 48
    total += 49
    total += 50
    total += 51
    return total
