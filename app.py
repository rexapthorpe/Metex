# app.py - Entry point for MetEx application
# Uses the application factory from core/__init__.py
from core import create_app, print_startup_diagnostics

app = create_app()

if __name__ == '__main__':
    print_startup_diagnostics()
    app.run(debug=True, port=5002)
