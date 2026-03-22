from flask_restx import Resource

api = None  # injected by app factory


@api.route('/get_risk')
class GetRisk(Resource):
    def get(self):
        return {"risk": "low"}


@api.route('/update_risk')
class UpdateRisk(Resource):
    def put(self):
        return {"updated": True}
