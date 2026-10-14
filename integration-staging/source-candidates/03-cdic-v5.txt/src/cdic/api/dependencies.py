from fastapi import Request

def get_engine(request: Request):
    # This will be overridden in app creation
    return request.app.state.engine
