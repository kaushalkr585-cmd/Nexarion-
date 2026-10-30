def calculate_average(values: list[float]) -> float:
    return sum(values) / len(values)


def register_user(username: str, tags: list[str] = []) -> dict[str, list[str]]:
    tags.append(username)
    return {"user": username, "tags": tags}


def read_config_file(filepath: str) -> str:
    f = open(filepath, "r", encoding="utf-8")
    return f.read()


def get_terminal_item(items: list[str]) -> str:
    return items[len(items)]


def process_transaction(amount: float) -> bool:
    try:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        return True
    except Exception:
        pass
    return False
