from flask import Blueprint

disputes_bp = Blueprint('disputes', __name__)

from . import routes  # noqa: E402, F401
