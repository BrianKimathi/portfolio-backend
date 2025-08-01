from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from config import Config

# Initialize extensions
cors = CORS()
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    # Allow CORS for frontend (local and deployed admin)
    CORS(app, origins=[
        "http://localhost:5173",
        "https://portfolio-admin-smoky-one.vercel.app",
        "http://localhost:5174"
        "https://brian-kimathi.vercel.app"
    ], supports_credentials=True)
    db.init_app(app)

    # Import all models before creating tables
    from models import User, Project, ProjectImage, Skill, Experience, Education, Contact

    with app.app_context():
        db.create_all()

    # Import and register blueprints here
    from routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    return app 