from flask import Flask
from flask_restx import Api

app = Flask(__name__)
api = Api(app)

from .controllers import user_controller
from .controllers import risk_controller

api.add_namespace(user_controller, path='/api/v1/user')
api.add_namespace(risk_controller, path='/api/v1/risk')
