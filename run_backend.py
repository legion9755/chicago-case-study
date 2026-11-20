"""
Start the Flask backend:   python run_backend.py
API base URL:              http://127.0.0.1:5000/api
"""
import os

from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("API_HOST", "127.0.0.1"), port=int(os.getenv("API_PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG", "0") == "1")
