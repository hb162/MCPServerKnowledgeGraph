from flask_restx import Resource

api = None  # injected by app factory


def validate_user(data):
    """Internal validation helper."""
    return data is not None


def format_response(result):
    """Internal format helper."""
    return {"data": result}


@api.route('/get_user')
class GetUser(Resource):
    def get(self):
        data = validate_user({"id": 1})
        return format_response(data)


@api.route('/create_user')
class CreateUser(Resource):
    def post(self):
        return format_response({"created": True})
