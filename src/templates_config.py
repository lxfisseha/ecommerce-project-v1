from fastapi.templating import Jinja2Templates
from fastapi import Request

def csrf_token_context_processor(request: Request):
    return {"csrf_token": request.scope.get("csrf_token")}

templates = Jinja2Templates(
    directory="src/templates",
    context_processors=[csrf_token_context_processor]
)
