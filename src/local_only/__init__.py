"""Version-pinned patches for the standalone packaged application."""


def replace_once(text, old, new):
    count = text.count(old)
    if count != 1:
        raise ValueError(f'Upstream anchor changed ({count} matches): {old[:100]}')
    return text.replace(old, new, 1)
