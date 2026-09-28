FROM python:3.12-alpine

COPY proxy.py /proxy.py

EXPOSE 8080

ENTRYPOINT ["python", "/proxy.py"]
CMD ["llama-server", "8081", "8080"]