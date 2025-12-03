import sqlite3

DB_PATH = "database.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    metal = "Gold"
    product_line = "Mexican Libertad"
    product_type = "Coin"
    weight = "1 oz"
    mint = "Mexican Mint"
    finish = "Reverse Proof"
    grade = "PF-70"  # you can change this later if you want

    # "Past 20 years" – adjust if you prefer a different span
    start_year = 2006
    end_year = 2025  # inclusive; 2006–2025 = 20 years

    for year in range(start_year, end_year + 1):
        name = f"{year} {metal} {product_line} {weight} {finish}"

        # Check if this category already exists to avoid duplicates
        existing = c.execute(
            """
            SELECT id FROM categories
            WHERE metal = ?
              AND product_line = ?
              AND product_type = ?
              AND weight = ?
              AND mint = ?
              AND year = ?
              AND finish = ?
              AND grade = ?
            """,
            (metal, product_line, product_type, weight, mint, year, finish, grade),
        ).fetchone()

        if existing:
            print(f"Category already exists for year {year}, id={existing['id']}")
            continue

        c.execute(
            """
            INSERT INTO categories (name, metal, product_line, product_type, weight, mint, year, finish, grade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, metal, product_line, product_type, weight, mint, year, finish, grade),
        )
        new_id = c.lastrowid
        print(f"Inserted category {name} with id={new_id}")

    conn.commit()
    conn.close()
    print("Done seeding Libertads.")


if __name__ == "__main__":
    main()
