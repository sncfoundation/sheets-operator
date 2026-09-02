# SheetsOperator as a container. Its image gets packed INTO a spreadsheet (SICF) and
# run by the cluster; it reconciles managed Google Sheets from the control plane.
# Google creds are MOUNTED at runtime (never baked into the image).
FROM python:3.12-slim
RUN pip install --no-cache-dir google-api-python-client google-auth
WORKDIR /app
COPY sheetsctl.py .
COPY templates ./templates
ENV SHEETSOP_CREDS=/creds/creds.json
ENTRYPOINT ["python","sheetsctl.py"]
CMD ["run","--interval","10"]
