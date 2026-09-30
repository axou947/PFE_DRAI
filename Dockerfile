FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY pfe_drai pfe_drai
RUN pip install --no-cache-dir -e ".[app]"
COPY . .
EXPOSE 8501 8000
# Dashboard by default; for the API: docker run -p 8000:8000 <image> uvicorn api.main:app --host 0.0.0.0
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0"]
