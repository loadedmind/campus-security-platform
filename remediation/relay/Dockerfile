FROM python:3.13-slim

RUN pip install --no-cache-dir PyYAML==6.0.3 \
 && useradd --system --uid 10001 remediator

WORKDIR /app
COPY remediator.py /app/remediator.py

USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2).status==200 else 1)"
ENTRYPOINT ["python", "/app/remediator.py"]
