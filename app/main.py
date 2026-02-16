from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
from io import StringIO

from .database import collection
from pathlib import Path

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Get all inquiries
    inquiries = list(collection.find().sort("timestamp", -1))
    
    # Convert ObjectId to str for display
    for inquiry in inquiries:
        inquiry["_id"] = str(inquiry["_id"])
        inquiry["timestamp"] = inquiry["timestamp"].isoformat()

    return templates.TemplateResponse("dashboard.html", {"request": request, "inquiries": inquiries})

@app.get("/export")
async def export_csv():
    inquiries = list(collection.find())
    
    # Convert to DataFrame
    for i in inquiries:
        i["_id"] = str(i["_id"])
    df = pd.DataFrame(inquiries)
    
    # Convert to CSV in memory
    stream = StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)
    
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inquiries.csv"}
    )
