import sys
sys.path.insert(0, '.')

print("\n=== CHECKING FLASK ROUTES ===\n")

try:
    from app import app
    print("Successfully imported app")

    print("\nAll registered routes:")
    portfolio_routes = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        route_str = f"{rule.methods} {rule}"
        if 'portfolio' in str(rule).lower():
            portfolio_routes.append(route_str)
        print(route_str)

    print(f"\n\nPortfolio routes found: {len(portfolio_routes)}")
    for route in portfolio_routes:
        print(f"  - {route}")

    if len(portfolio_routes) == 0:
        print("\nERROR: No portfolio routes found!")
        print("Checking if portfolio_bp was imported...")
        try:
            from routes.portfolio_routes import portfolio_bp
            print(f"  portfolio_bp exists: {portfolio_bp}")
            print(f"  Blueprint name: {portfolio_bp.name}")
        except Exception as e:
            print(f"  ERROR importing portfolio_bp: {e}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
