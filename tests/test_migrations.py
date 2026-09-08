from commerce_support.repository import SQLiteRepository


def test_clean_database_contains_all_business_tables(repository: SQLiteRepository) -> None:
    with repository.connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {
        "users",
        "orders",
        "order_items",
        "logistics",
        "approvals",
        "tickets",
        "eval_runs",
    }.issubset(tables)
